"""Implementation of Prometheus client to fetch sensor values from Sesame lock."""

# Standard library imports
import functools
import logging
import sys
import threading
import time
from concurrent import futures
from typing import Any, Dict, Final, Mapping, Tuple

# Third‑party imports
import prometheus_client
import requests

logging.basicConfig(
    level=logging.INFO,
    format=("%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

# Cache wait time before refreshing from API
_CACHE_TTL = 7200  # 2 hours

_SESAME_API_URL_TEMPLATE: Final[str] = "https://app.candyhouse.co/api/sesame2/{}"

# Keys are as defined by the Sesame API's contract.
# See: https://document.candyhouse.co/demo/webapi-en#1get-the-status-of-sesame
# Values are the Prometheus custom metrics for the key.
_METRICS_KEYS: Final[Mapping[str, prometheus_client.Gauge]] = {
    "batteryVoltage": prometheus_client.Gauge(
        "sesame_battery_voltage", "Battery Voltage", labelnames=("device",)
    ),
    "batteryPercentage": prometheus_client.Gauge(
        "sesame_battery_percent", "Battery Percentage", labelnames=("device",)
    ),
}

_PROMETHEUS_LOCK = threading.Lock()


def ttl_cache(timeout: int):
    """Decorator to cache function results for a given timeout."""
    cache: Dict[Tuple[Any, ...], Tuple[Any, float]] = {}
    lock = threading.Lock()

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, disable_cache: bool = False, **kwargs) -> Tuple[Any, bool]:
            key = (args, tuple(kwargs.items()))

            # Check if the function is already cached in a thread-safe manner
            # and if the cache is still valid, and if the cache is not disabled.
            with lock:
                if key in cache and disable_cache is False:
                    result, timestamp = cache[key]
                    if time.time() - timestamp < timeout:
                        return result, True

            result = func(*args, **kwargs)
            with lock:
                cache[key] = (result, time.time())

                return result, False

        return wrapper

    return decorator


@ttl_cache(timeout=_CACHE_TTL)
def _get_metrics(sesame_name: str, uuid: str, api_key: str) -> dict[str, Any]:
    """Fetch metrics from the Sesame API."""

    url = _SESAME_API_URL_TEMPLATE.format(uuid)
    headers = {"x-api-key": api_key}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        return res.json()  # type: ignore[no-any-return]

    except requests.exceptions.RequestException as e:
        logging.error(
            "Error fetching metrics from API for %s: %s %s",
            sesame_name,
            type(e).__name__,
            e,
        )
        raise RuntimeError(f"Failed to fetch metrics for {sesame_name}") from e


# update metrics in multiple threads
def update_metrics(uuids: Dict[str, str], api_key: str):
    """Main routine to update metrics."""

    def _process_device(sesame_name, uuid) -> None:
        """Fetch and update metrics for a single device."""

        max_retries = 8  # maximum number of retries before giving up
        backoff_factor = 2  # exponential backoff factor
        base_delay = 60
        attempt = 1

        disable_cache = False  # flag to disable cache after a failure

        def _remove_gauge(metric_key: str) -> None:
            """Remove a gauge if it exists."""
            with _PROMETHEUS_LOCK:
                try:
                    _METRICS_KEYS[metric_key].remove(sesame_name)
                except KeyError:
                    pass

        def _remove_gauges() -> None:
            """Remove gauges if any of it exists."""
            for key in _METRICS_KEYS:
                _remove_gauge(key)

        def _exponential_backoff() -> None:
            """Calculate the delay for exponential backoff."""
            nonlocal attempt

            delay = base_delay * (backoff_factor ** (attempt - 1))
            logging.info(
                "Retrying %s in %d seconds (attempt %d/%d)",
                sesame_name,
                delay,
                attempt,
                max_retries,
            )
            time.sleep(delay)
            attempt += 1

        while attempt <= max_retries:
            # Fetch metrics with exponential backoff
            try:
                metrics, cached = _get_metrics(
                    sesame_name, uuid, api_key, disable_cache=disable_cache
                )
                if cached:
                    return

            except RuntimeError as e:
                logging.error(
                    "Failed to fetch metrics for %s: %s %s",
                    sesame_name,
                    type(e).__name__,
                    e,
                )

                _remove_gauges()
                _exponential_backoff()
                disable_cache = True
                continue

            logging.info(f"Fetched new metrics ({metrics}) for {sesame_name}")

            # Undocumented API response on failure
            if "success" in metrics and metrics.get("success") is False:
                logging.error(
                    f"Failed to process metrics ({metrics}) for {sesame_name}"
                )

                _remove_gauges()
                _exponential_backoff()
                disable_cache = True
                continue

            all_metrics_success = True
            for key in _METRICS_KEYS:
                metric = metrics.get(key)

                if metric is None:
                    logging.warning(f"Failed to update metric for {sesame_name}: {key}")
                    _remove_gauge(key)
                    all_metrics_success = False
                    continue

                # Update metric in a thread-safe manner.
                with _PROMETHEUS_LOCK:
                    _METRICS_KEYS[key].labels(device=sesame_name).set(float(metric))
                    logging.info(
                        f"Updated metric for {sesame_name}: {key}: {float(metric)}"
                    )

            if not all_metrics_success:
                logging.error(f"Failed to update some metrics for {sesame_name}")
                _exponential_backoff()
                disable_cache = True
                continue

            return  # Return if successful

        # If we reach here, it means we exhausted all retries.
        # Just give up and log an error.
        logging.error(
            "Failed to fetch and update some or all metrics for %s after %d attempts",
            sesame_name,
            max_retries,
        )
        return

    # Process each device's metrics in parallel
    with futures.ThreadPoolExecutor() as executor:
        threads = [
            executor.submit(_process_device, name, uuid) for name, uuid in uuids.items()
        ]
        for thread in threads:
            thread.result()
