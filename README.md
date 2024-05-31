# event-test-harness
Test harness to simulate update events to send to an event broker

From this test harness interface you can query data from a SPARQL endpoint and send an event to various event brokers, primarily for testing RDF update events.

## Testing a SPARQL endpoint

This test harness includes a simple test interface to check connectivity to a SPARQL endpoint to receive some RDF data. The primary intended use case for the event test harness is to pass through a patch-log update event where an RDF delta server will process the update. 

## Test sending an event

This test harness has been tested with Azure Service Bus, and in future will support Azure Event Hub and Kafka.

## Environment Variables

### SPARQL configuration

|Env variable| Value                                   | Description           |
|------------|-----------------------------------------|-----------------------|
|SPARQL_ENDPOINT| e.g., https://query.wikidata.org/sparql | SPARQL endpoint to query

### Azure Service Bus Environment Variables

|Env variable| Value                  | Description           |
|------------|------------------------|-----------------------|
|EVENT_BROKER_TYPE| AzureServiceBus        | Uses the Azure Service Bus (ASB) adapter |
|EVENT_BROKER_TOPIC| <topic-name> | Name of the ASB topic |
|EVENT_BROKER_ENDPOINT| e.g. sb://<name-space>.servicebus.windows.net/| ASB endpoint URL| 
|EVENT_BROKER_NAME|<name-space>|Namespace provided when setting up ASB|

### Azure Auth Environment Settings

|Env variable| Value                   | Description           |
|------------|-------------------------|-----------------------|
|AUTH_MODE| shared_access_key, msal | The auth mode to use|
|MS_TENANT_ID|e.g., xxxxx-xxx-xxx-xxx-xxxxx|From Azure portal|

### SAS Token
|Env variable| Value                                             | Description                           |
|------------|---------------------------------------------------|---------------------------------------|
|AUTH_MODE| shared_access_key                                 | Use a SAS token                       |
|SAS_TOKEN| <token>, e.g. Endpoint=...;...SharedAccessKey=... | Connection string including the token |


### MSAL

| Env variable       | Value                | Description             |
|--------------------|----------------------|-------------------------|
| AUTH_MODE          | msal                 | Use MSAL                |
| MSAL_CLIENT_ID     | <your_client_id>     | Your MSAL client id     |
| MSAL_AUTHORITY     | <your_authority_url> | Your MSAL authority url |
| MSAL_CLIENT_SECRET | <your_client_secret> | Your MSAL client secret |


## Example environment settings

1. SPARQL endpoint, Azure Service Bus using a SAS Token

```
SPARQL_ENDPOINT=https://query.wikidata.org/sparql

EVENT_BROKER_TYPE=AzureServiceBus
EVENT_BROKER_TOPIC=test-topic
EVENT_BROKER_ENDPOINT=sb://testbus.servicebus.windows.net/
EVENT_BROKER_NAME=testbus

AUTH_MODE=shared_access_key
SAS_TOKEN=Endpoint=sb://testbus.servicebus.windows.net/;SharedAccessKeyName=test-key;SharedAccessKey=aaaAAA/bbbEEE/cccCCC+dddDDD=
MS_TENANT_ID=11111111=aaaa-222-3333-4444444444

