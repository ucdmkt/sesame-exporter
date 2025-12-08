# Sesame Exporter

A Prometheus exporter for the [Sesame smart lock API](https://document.candyhouse.co/demo/webapi-en).

## Description

This package exposes battery voltage and percentage metrics from your Sesame smart locks to Prometheus. It queries the Sesame Web API and serves the metrics on a specified port.

## Installation

```bash
pip install sesame-exporter
```

## Usage

You need a generic API key from the Sesame Dashboard.

Set the `SESAME_WEB_API_KEY` environment variable:
```bash
export SESAME_WEB_API_KEY="your-api-key"
```

Run the exporter:
```bash
sesame-exporter --port 8000 --sesame-uuid "MyLock=YOUR_UUID"
```

### Configuration File

You can also use a YAML configuration file:

```yaml
port: 8000
sesame_uuids:
  FrontDoor: "UUID-1"
  BackDoor: "UUID-2"
```

Run with config:
```bash
sesame-exporter --config config.yaml
```

## Docker Deployment

You can deploy the exporter alongside Prometheus using Docker Compose.

1.  Set your API key in your shell:
    ```bash
    export SESAME_WEB_API_KEY="your-api-key"
    ```

2.  Start the services:
    ```bash
    docker-compose up -d
    ```

    This launches:
    -   **sesame-exporter**: Port 8000 (internal)
    -   **prometheus**: Port 9090 (accessible at http://localhost:9090)

### Prometheus Configuration

The included `prometheus.yaml` is pre-configured to scrape the exporter:

```yaml
scrape_configs:
  - job_name: sesame
    static_configs:
      - targets: ["sesame-exporter:8000"]
    scrape_interval: 1m
```

## Metrics

| Metric | Description | Labels |
|Str|Str|Str|
|---|---|---|
| `sesame_battery_voltage` | Battery Voltage | `device` (Name of the lock) |
| `sesame_battery_percent` | Battery Percentage | `device` (Name of the lock) |

## Development

Install dependencies:
```bash
pip install -r requirements-dev.txt
pip install -e .
pre-commit install
```

Run tests:
```bash
pytest
```

Run linters (via pre-commit):
```bash
pre-commit run --all-files
```

## License

Apache License 2.0
