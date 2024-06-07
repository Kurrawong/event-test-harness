# event-test-harness

| product           | status    |
| ----------------- | --------- |
| Azure Service bus | supported |
| Azure event hub   | planned   |
| kafka             | planned   |

Event broker test harness, to test messaging function and connectivity between
applications. Current configuration includes two applications, a producer and a consumer.

**Producer**

Test harness for:

- sending sparql queries to a sparql endpoint
- sending events to a message broker topic

**Consumer**

Test harness for:

- viewing messages on an event broker topic
- consuming messages from the topic (in the form of submitting rdf as a patch to an RDF delta server)
- viewing the rdf delta server patch log

## Running locally

```bash
poetry install
poetry run python src/producer.py
poetry run python src/consumer.py
```

## Building the images

```bash
docker build . -f Dockerfile-producer -t testharness-producer
docker build . -f Dockerfile-consumer -t testharness-consumer
```

## Environment Variables

The following environment variables are required:

- `BROKER_CONNECTION_STR`: (the azure servicebus connection string to use)

The rest of the environment variables are optional and can be set in the UI after starting the application.

| Env variable          | Value                                             | Description                              |
| --------------------- | ------------------------------------------------- | ---------------------------------------- |
| sparl                 |                                                   |                                          |
| SPARQL_ENDPOINT       | e.g., https://query.wikidata.org/sparql           | SPARQL endpoint to query                 |
| BROKER_TYPE           | AzureServiceBus                                   | Uses the Azure Service Bus (ASB) adapter |
| BROKER_TOPIC          | <topic-name>                                      | Name of the ASB topic                    |
| BROKER_ENDPOINT       | e.g. sb://<name-space>.servicebus.windows.net/    | ASB endpoint URL                         |
| BROKER_NAME           | <name-space>                                      | Namespace provided when setting up ASB   |
| auth                  |                                                   |                                          |
| AUTH_MODE             | shared_access_key (default), msal                 | The auth mode to use                     |
| shared_access_key     |                                                   |                                          |
| BROKER_CONNECTION_STR | <token>, e.g. Endpoint=...;...SharedAccessKey=... | Connection string including the token    |
| msal                  |                                                   |                                          |
| MS_TENANT_ID          | e.g., xxxxx-xxx-xxx-xxx-xxxxx                     | From Azure portal                        |
| MSAL_CLIENT_ID        | <your_client_id>                                  | Your MSAL client id                      |
| MSAL_AUTHORITY        | <your_authority_url>                              | Your MSAL authority url                  |
| MSAL_CLIENT_SECRET    | <your_client_secret>                              | Your MSAL client secret                  |
