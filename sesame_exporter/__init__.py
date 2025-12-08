"""Sesame API client and Prometheus Exporter."""

import argparse
import logging
import os
import sys
import time
from typing import Final

import prometheus_client
import yaml

from sesame_exporter._impl import update_metrics

_DEFAULT_PORT: Final[int] = 8000

# Poll every 10 seconds. there is also client-side caching in client implementation.
_POLL_INTERVAL: Final[int] = 10


def _parse_args():
    """Parse command line arguments with config file override."""
    # Pass 1: Check for config file
    conf_parser = argparse.ArgumentParser(add_help=False)
    conf_parser.add_argument("--config", help="Path to configuration file")
    args, remaining_argv = conf_parser.parse_known_args()

    defaults = {
        "port": _DEFAULT_PORT,
        "sesame_uuids": {},
    }

    if args.config:
        try:
            with open(args.config, "r") as f:
                config_data = yaml.safe_load(f)
                if config_data:
                    defaults.update(config_data)
        except FileNotFoundError:
            logging.error(f"Config file not found: {args.config}")
            sys.exit(1)
        except yaml.YAMLError as e:
            logging.error(f"Error parsing YAML config file: {e}")
            sys.exit(1)
        except OSError as e:
            logging.error(f"Error reading config file: {e}")
            sys.exit(1)

    # Pass 2: Parse all arguments
    parser = argparse.ArgumentParser(
        description="Sesame API Prometheus Exporter",
        parents=[conf_parser],  # Inherit config option
    )
    parser.set_defaults(**defaults)

    parser.add_argument(
        "--port", type=int, help=f"Port to expose metrics on (default: {_DEFAULT_PORT})"
    )
    parser.add_argument(
        "--sesame-uuid",
        action="append",
        help="Sesame UUID in format Name=UUID",
    )
    parser.add_argument("--once", action="store_true", help="Run once and exit")

    args = parser.parse_args(remaining_argv)

    # Merge CLI UUIDs into defaults/config UUIDs
    # CLI args take precedence or append? "Override" usually means replace or update.
    # Here we treat CLI --sesame-uuid as adding/overwriting specific keys.
    if args.sesame_uuid:
        for item in args.sesame_uuid:
            if "=" in item:
                key, value = item.split("=", 1)
                defaults["sesame_uuids"][key] = value
            else:
                logging.error(f"Invalid format for --sesame-uuid: {item}")
                sys.exit(1)

    args.sesame_uuids = defaults["sesame_uuids"]
    return args


def main() -> None:
    args = _parse_args()

    # Validate required environment variable
    api_key = os.getenv("SESAME_WEB_API_KEY")
    if not api_key:
        logging.error("SESAME_WEB_API_KEY environment variable not set")
        sys.exit(1)

    if not args.sesame_uuids:
        logging.error("No Sesame UUIDs configured.")
        sys.exit(1)

    if args.once:
        update_metrics(args.sesame_uuids, api_key)
        return

    # expose metrics in a web server
    logging.info(f"Starting Prometheus server on port {args.port}")
    prometheus_client.start_http_server(args.port)

    # update metrics forever
    while True:
        update_metrics(args.sesame_uuids, api_key)
        time.sleep(_POLL_INTERVAL)
