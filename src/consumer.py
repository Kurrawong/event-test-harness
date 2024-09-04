import html
import logging
import os
import sys
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

import uvicorn
from azure.servicebus import (ServiceBusClient, ServiceBusMessage,
                              ServiceBusReceiver, TransportType)
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Template
from rdf_delta import DeltaClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(levelname)s:  %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


# Get environment variables

load_dotenv()

broker_topic = os.getenv("BROKER_TOPIC", "")
broker_endpoint = os.getenv("BROKER_ENDPOINT", "")
broker_subscription = os.getenv("BROKER_SUBSCRIPTION", "")
broker_connection_str = os.getenv("BROKER_CONNECTION_STR", "")

rdfdelta_endpoint = os.getenv("RDFDELTA_ENDPOINT", "")
rdfdelta_datasource = os.getenv("RDFDELTA_DATASOURCE", "")

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
            "broker_connection_str": broker_connection_str[:25]
            + "..."
            + broker_connection_str[-12:],
            "rdfdelta_endpoint": rdfdelta_endpoint,
            "rdfdelta_datasource": rdfdelta_datasource,
        },
    )


@app.post("/peek")
async def peek(
    request: Request,
    broker_endpoint: str = Form(...),
    broker_topic: str = Form(...),
    broker_subscription: str = Form(...),
    peek_messages: int = Form(...),
):
    servicebus_client = ServiceBusClient.from_connection_string(
        broker_connection_str,
        transport_type=TransportType.AmqpOverWebsocket,
    )
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
    servicebus_client = ServiceBusClient.from_connection_string(
        broker_connection_str, transport_type=TransportType.AmqpOverWebsocket
    )
    reciever = servicebus_client.get_subscription_receiver(
        topic_name=broker_topic, subscription_name=broker_subscription
    )
    messages = reciever.receive_messages(max_message_count=1, max_wait_time=1)
    logger.debug(messages)
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
    if not broker_connection_str:
        logger.error("BROKER_CONNECTION_STR not set", "")
        exit()
    env_vars = "\n".join(
        [
            "ENV VARS",
            broker_topic,
            broker_endpoint,
            broker_subscription,
            broker_connection_str,
            rdfdelta_endpoint,
            rdfdelta_datasource,
        ]
    )
    logger.debug(env_vars)
    uvicorn.run("consumer:app", host="127.0.0.1", port=8080, reload=True)
