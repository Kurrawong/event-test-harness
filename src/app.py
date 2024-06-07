import uvicorn
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
import os
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from msal import ConfidentialClientApplication
from azure.eventhub import EventHubProducerClient, EventData
#from confluent_kafka import Producer
import json
import requests

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()


def get_summary(**kwargs):
    summary_parts = []

    for var_name, var_value in kwargs.items():
        if var_value:
            value_str = str(var_value)
            formatted_value = f"{value_str[:3]}...{value_str[-3:]}"
            summary_parts.append(f"{var_name} = {formatted_value}")

    return ", ".join(summary_parts)

# Get environment variables
default_event_broker_topic = os.getenv("EVENT_BROKER_TOPIC")
event_broker_name = os.getenv("EVENT_BROKER_NAME")
event_broker_endpoint = os.getenv("EVENT_BROKER_ENDPOINT")

sparql_endpoint = os.getenv("SPARQL_ENDPOINT")
auth_mode = os.getenv("AUTH_MODE")
sas_token = os.getenv("SAS_TOKEN")
tenant_id = os.getenv("MS_TENANT_ID")
client_id = os.getenv("MSAL_CLIENT_ID")
authority = os.getenv("MSAL_AUTHORITY")
client_secret = os.getenv("MSAL_CLIENT_SECRET")
sparql_query = "CONSTRUCT WHERE {?s ?p ?o} LIMIT 10"
sparql_content_type = "text/ttl"

summary = f"AUTH_MODE={auth_mode}, " + get_summary(
    SAS_TOKEN=sas_token,
    MS_TENANT_ID=tenant_id,
    MSAL_CLIENT_ID=client_id,
    MSAL_AUTHORITY=authority,
    MSAL_CLIENT_SECRET=client_secret
)

app = FastAPI()

form_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Event Broker Configuration</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bulma/0.9.3/css/bulma.min.css">
</head>
<body>
    <section class="section">
        <h1 class="title">Event Test Harness</h1>
        <p>
            Use the test harness to test reading from a SPARQL endpoint and to push a message to an event broker topic.
        </p>
        <br />
        <div class="columns">
            <form class="container column is-half" action="/data" method="POST">
                <h2 class="subtitle"><b>Test SPARQL configuration</b></h2>
                <hr />
                <div class="field">
                    <label class="label">SPARQL endpoint</label>
                    <div class="control">
                        <input class="input" type="text" name="sparql_endpoint" value="{sparql_endpoint}" placeholder="Readonly SPARQL endpoint" />
                    </div>
                </div>
                <div class="field">
                    <label class="label">SPARQL content type</label>
                    <div class="control">
                        <div class="select">
                            <select name="sparql_content_type">
                                <option value="text/turtle" {{ "selected" if sparql_content_type == "text/turtle" else "" }}>Turtle</option>
                                <option value="application/json" {{ "selected" if sparql_content_type == "application/json" else "" }}>JSON</option>
                            </select>
                        </div>
                    </div>
                </div>
                
                <div class="field">
                    <label class="label">SPARQL query</label>
                    <div class="control">
                        <textarea class="textarea" name="sparql_query" placeholder="Enter your SPARQL query">{sparql_query}</textarea>
                    </div>
                </div>
                <div class="field">
                    <div class="control">
                        <button class="button is-primary" type="submit">Send Query</button>
                    </div>
                </div>
                <div class="field">
                    <label class="label">Query Response</label>
                    <div class="control">
                        <textarea style="height:16rem;" class="textarea" readonly>{query_response}</textarea>
                    </div>
                </div>
            </form>
            <form class="container column is-half" action="/event" method="POST">
                <h1 class="subtitle" title="{summary}"><b>Test Event Broker Configuration</b></h1>
                <hr />
                <div class="field">
                    <label class="label">Event Broker Type</label>
                    <div class="control">
                        <div class="select">
                            <select name="event_broker_type">
                                <option value="AzureServiceBus" {{ "selected" if event_broker_type == "AzureServiceBus" else "" }}>Azure Service Bus</option>
                                <option value="EventHub" {{ "selected" if event_broker_type == "EventHub" else "" }}>Event Hub</option>
                                <!-- <option value="Kafka" {{ "selected" if event_broker_type == "Kafka" else "" }}>Kafka</option> -->
                            </select>
                        </div>
                    </div>
                </div>
                <div class="field">
                    <label class="label">Event Broker Endpoint</label>
                    <div class="control">
                        <input class="input" type="text" name="event_broker_endpoint" value="{event_broker_endpoint}" placeholder="Event Broker Endpoint" />
                    </div>
                </div>
                <div class="field">
                    <label class="label">Event Broker Topic</label>
                    <div class="control">
                        <input class="input" type="text" name="event_broker_topic" value="{event_broker_topic}" placeholder="Event Broker Topic" />
                    </div>
                </div>
                <div class="field">
                    <label class="label">Subject</label>
                    <div class="control">
                        <input class="input" type="text" name="subject" placeholder="Enter your subject here" />
                    </div>
                </div>
                <div class="field">
                    <label class="label">Message</label>
                    <div class="control">
                        <textarea class="textarea" name="message" placeholder="Enter your message here"></textarea>
                    </div>
                </div>
                <div class="field">
                    <div class="control">
                        <button class="button is-primary" type="submit">Send Message</button>
                    </div>
                </div>
                <div class="field">
                    <div class="control">
                        <textarea class="textarea" readonly>{status_message}</textarea>
                    </div>
                </div>
            </form>
        </div>
    </section>
    <hr />
    <p>
        <center>
            <img style="width: 100px;" src="https://kurrawong.ai/KurrawongAI_350.png" />
        </center>
    </p>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def show_form():
    return form_template.format(summary=summary, event_broker_type="", event_broker_topic=default_event_broker_topic,
                                event_broker_endpoint=event_broker_endpoint, status_message="", subject="", message="",
                                sparql_endpoint=sparql_endpoint, sparql_content_type=sparql_content_type, sparql_query=sparql_query, query_response="")


@app.post("/data", response_class=HTMLResponse)
async def sparql_query_endpoint(sparql_endpoint: str = Form(...), sparql_content_type: str = Form(...),
                                sparql_query: str = Form(...)):
    try:
        headers = {
            "Accept": sparql_content_type,
            "Content-Type": "application/sparql-query"
        }
        response = requests.post(sparql_endpoint, data=sparql_query, headers=headers)
        response.raise_for_status()
        query_response = response.text
    except Exception as e:
        query_response = f"Error performing SPARQL query: {str(e)}"

    return form_template.format(summary=summary, event_broker_type="", event_broker_topic=default_event_broker_topic,
                                event_broker_endpoint=event_broker_endpoint, status_message="", subject="", message="",
                                sparql_endpoint=sparql_endpoint, sparql_content_type=sparql_content_type,
                                sparql_query=sparql_query, query_response=query_response)


@app.post("/event", response_class=HTMLResponse)
async def submit_form(event_broker_type: str = Form(...), event_broker_endpoint: str = Form(...),
                      event_broker_topic: str = Form(...), subject: str=Form(...), message: str = Form(...)):
    status_message = ""  # Initialize status message

    # Depending on the event broker type, handle the message accordingly
    if event_broker_type == "AzureServiceBus":
        try:
            if auth_mode == "msal":
                # Connect to Azure Service Bus using MSAL authentication
                app = ConfidentialClientApplication(
                    client_id,
                    authority=f"https://login.microsoftonline.com/{tenant_id}",
                    client_credential=client_secret
                )
                token_response = app.acquire_token_for_client(scopes=["https://servicebus.azure.net/.default"])
                access_token = token_response["access_token"]

                servicebus_client = ServiceBusClient.from_connection_string(
                    f"Endpoint={event_broker_endpoint};SharedAccessSignature=Bearer {access_token}"
                )
            elif auth_mode == "shared_access_key":
                # Connect to Azure Service Bus using Shared Access Key
                servicebus_client = ServiceBusClient.from_connection_string(
                    f"{sas_token}"
                )
                # Endpoint={event_broker_endpoint};SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey={sas_token}...
            else:
                raise ValueError("Invalid auth mode specified")

            # Send message to Azure Service Bus
            sender = servicebus_client.get_topic_sender(topic_name=event_broker_topic)
            sender.send_messages(ServiceBusMessage(subject=subject, body=message))
            servicebus_client.close()

            status_message = "Message sent successfully to Azure Service Bus"
        except Exception as e:
            status_message = f"Error sending message to Azure Service Bus: {str(e)}"

    elif event_broker_type == "EventHub":
        try:
            # Send message to Event Hub using EventHubProducerClient
            event_hub_client = EventHubProducerClient.from_connection_string(sas_token, eventhub_name=event_broker_topic)
            event_data_batch = event_hub_client.create_batch()
            event_data_batch.add(json.dumps({"message": message}))
            send_result = event_hub_client.send_batch(event_data_batch)
            event_hub_client.close()

            if send_result:
                status_message = "Message sent successfully to Event Hub"
            else:
                status_message = "Error sending message to Event Hub"
        except Exception as e:
            status_message = f"Error sending message to Event Hub: {str(e)}"

    # elif event_broker_type == "Kafka":
    #     try:
    #         # Send message to Kafka
    #         kafka_producer = Producer({"bootstrap.servers": event_broker_endpoint})
    #         delivery_report = kafka_producer.produce(event_broker_topic,
    #                                                  json.dumps({"message": message}).encode("utf-8"))
    #         kafka_producer.flush()
    #
    #         if delivery_report.error() is None:
    #             status_message = "Message sent successfully to Kafka"
    #         else:
    #             status_message = f"Error sending message to Kafka: {delivery_report.error()}"
    #     except Exception as e:
    #         status_message = f"Error sending message to Kafka: {str(e)}"

    # Reload the form with the submitted values and status message displayed
    return form_template.format(summary=summary, event_broker_type=event_broker_type, event_broker_topic=event_broker_topic,
                                event_broker_endpoint=event_broker_endpoint, status_message=status_message,
                                sparql_endpoint=sparql_endpoint, sparql_content_type=sparql_content_type,
                                sparql_query=sparql_query, query_response=""
                                )


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
