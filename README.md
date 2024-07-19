# event-test-harness

| product           | status    |
| ----------------- | --------- |
| Azure Service bus | supported |
| Azure event hub   | planned   |
| kafka             | planned   |

Event broker test harness, to test messaging function and connectivity between
applications. Current configuration includes two applications, a producer and a consumer.
It also includes simple test images for rdf-delta-server and rdf-delta-fuseki-server

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

> First you need to build and extract the rdf-delta-server and rdf-delta-fuseki-server jars and place
them in the project root. Source code can be cloned from https://github.com/afs/rdf-delta. building
requires maven and jdk17.


```bash
docker build . -f Dockerfile-producer -t testharness-producer
docker build . -f Dockerfile-consumer -t testharness-consumer
docker build . -f Dockerfile-rdf-delta-server -t rdf-delta-server
docker build . -f Dockerfile-rdf-delta-fuseki-server -t rdf-delta-fuseki-server
```
