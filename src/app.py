import html
import logging
import os
import sys
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

import requests
import uvicorn
from azure.servicebus import ServiceBusClient, ServiceBusMessage, ServiceBusReceiver
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import Template
from rdf_delta import DeltaClient


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


# Get environment variables

load_dotenv()

sparql_endpoint = os.getenv("SPARQL_ENDPOINT")
sparql_update_endpoint = os.getenv("SPARQL_UPDATE_ENDPOINT")

broker_topic = os.getenv("BROKER_TOPIC")
broker_endpoint = os.getenv("BROKER_ENDPOINT")
broker_subscription = os.getenv("BROKER_SUBSCRIPTION")
broker_connection_str = os.getenv("BROKER_CONNECTION_STR") or input("broker_connection_str: ")

rdfdelta_endpoint = os.getenv("RDFDELTA_ENDPOINT")
rdfdelta_datasource = os.getenv("RDFDELTA_DATASOURCE")

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def rdf_to_patch(rdf: str) -> str:
    dc = DeltaClient(rdfdelta_endpoint)
    ds = dc.describe_datasource(rdfdelta_datasource)
    ds_log = dc.describe_log(ds.id)
    last_patch_id = ds_log.latest
    patch = dedent(
        Template(
            """
        H id <uuid:{{ new_id }}> .
        {% if latest_id %}H prev <uuid:{{ latest_id }}> .{% endif %}

        TX .
        {% for line in lines %}
        A {{ line }}
        {% endfor %}
        TC .
        """
        ).render(latest_id=last_patch_id, new_id=(uuid4()), lines=rdf.split("\n"))
    )
    logger.debug(patch)
    return patch


def submit_patch(patch: str) -> None:
    dc = DeltaClient(rdfdelta_endpoint)
    dc.create_log(patch, rdfdelta_datasource)
    return


def process_message(msg: ServiceBusMessage, reciever: ServiceBusReceiver) -> None:
    if msg.subject == "rdf":
        rdf = msg.body.__next__().decode()
        patch = rdf_to_patch(rdf)
        submit_patch(patch)
    reciever.complete_message(msg)
    return


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "broker_endpoint": broker_endpoint,
            "broker_topic": broker_topic,
            "broker_subscription": broker_subscription,
            "broker_connection_str": broker_connection_str[:25] + "..." + broker_connection_str[-12:],
            "rdfdelta_endpoint": rdfdelta_endpoint,
            "rdfdelta_datasource": rdfdelta_datasource,
            "sparql_endpoint": sparql_endpoint,
            "sparql_update_endpoint": sparql_update_endpoint,
        },
    )


@app.post("/update")
async def sparql_update(
    sparql_update_endpoint: str = Form(...),
    sparql_update_query: str = Form(...),
):
    response = requests.post(
        sparql_update_endpoint, data={"update": sparql_update_query}
    )
    response.raise_for_status()
    logger.debug(response)
    return HTMLResponse(response.text)


@app.post("/query")
async def sparql_select(
    sparql_endpoint: str = Form(...),
    sparql_query: str = Form(...),
):
    headers = {
        "Accept": "text/csv",
        "Content-Type": "application/sparql-query",
    }
    response = requests.post(sparql_endpoint, data=sparql_query, headers=headers)
    response.raise_for_status()
    query_response = response.text
    logger.debug(query_response)
    content = html.escape(query_response).replace("\n", "<br>")
    return Response(content=content, media_type="text/csv")


@app.post("/produce")
async def produce(
    request: Request,
    broker_endpoint: str = Form(...),
    broker_topic: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
):
    servicebus_client = ServiceBusClient.from_connection_string(broker_connection_str)
    sender = servicebus_client.get_topic_sender(topic_name=broker_topic)
    sender.send_messages(ServiceBusMessage(subject=subject, body=body))
    servicebus_client.close()
    message = "Message sent successfully to Azure Service Bus"
    return HTMLResponse(content=message)


@app.post("/peek")
async def peek(
    request: Request,
    broker_endpoint: str = Form(...),
    broker_topic: str = Form(...),
    broker_subscription: str = Form(...),
    peek_messages: int = Form(...),
):
    servicebus_client = ServiceBusClient.from_connection_string(broker_connection_str)
    reciever = servicebus_client.get_subscription_receiver(
        topic_name=broker_topic, subscription_name=broker_subscription
    )
    messages = reciever.peek_messages(max_message_count=peek_messages)
    servicebus_client.close()
    if messages:
        return templates.TemplateResponse(
            "messages.html", {"request": request, "messages": messages}
        )
    message = "No pending messages"
    return HTMLResponse(content=message)


@app.post("/consume")
async def consume(
    request: Request,
    broker_endpoint: str = Form(...),
    broker_topic: str = Form(...),
    broker_subscription: str = Form(...),
    rdfdelta_endpoint: str = Form(...),
    rdfdelta_datasource: str = Form(...),
):
    servicebus_client = ServiceBusClient.from_connection_string(broker_connection_str)
    reciever = servicebus_client.get_subscription_receiver(
        topic_name=broker_topic, subscription_name=broker_subscription
    )
    messages = reciever.receive_messages(max_message_count=1, max_wait_time=1)
    if messages:
        msg = messages[0]
        process_message(msg, reciever)
        message = f"Processed message {msg.sequence_number}"
    else:
        message = "No messages to consume"
    reciever.close()
    servicebus_client.close()
    return HTMLResponse(status_code=200, content=message)


@app.post("/log")
async def get_log(
    request: Request,
    rdfdelta_endpoint: str = Form(...),
    rdfdelta_datasource: str = Form(...),
):
    dc = DeltaClient(rdfdelta_endpoint)
    ds = dc.describe_datasource(rdfdelta_datasource)
    ds_log = dc.describe_log(ds.id)
    log = dc.get_log(ds_log.max_version, datasource=rdfdelta_datasource)
    logger.debug(log)
    return HTMLResponse(content=html.escape(log).replace("\n", "<br>"))


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
