from unittest.mock import MagicMock, patch

import pytest
import requests
import yaml

from sesame_exporter import _impl as sesame
from sesame_exporter import _parse_args


# Fixtures
@pytest.fixture
def mock_get():
    with patch("requests.get") as mock:
        yield mock


@pytest.fixture
def mock_prometheus():
    with patch("prometheus_client.Gauge") as mock:
        yield mock


@pytest.fixture
def reset_metrics():
    # Reset metrics keys to a known state before each test
    # This assumes _METRICS_KEYS values are mocks or we can manipulate them
    # But in sesame.py they are real Gauges.
    # For testing update_metrics logic, we mock _METRICS_KEYS
    pass


def test_get_metrics_success(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "batteryVoltage": 3.0,
        "batteryPercentage": 50,
    }
    mock_get.return_value = mock_response

    metrics, cached = sesame._get_metrics("HOME_FRONT", "uuid", "api_key")
    assert metrics == {"batteryVoltage": 3.0, "batteryPercentage": 50}
    assert cached is False


def test_get_metrics_failure(mock_get):
    mock_get.side_effect = requests.exceptions.RequestException("API error")

    with pytest.raises(RuntimeError):
        sesame._get_metrics("HOME_FRONT", "uuid_fail", "api_key")


def test_ttl_cache():
    mock_func = MagicMock()
    mock_func.return_value = "test_result"

    cached_func = sesame.ttl_cache(timeout=1)(mock_func)

    # First call, should not be cached
    result, cached = cached_func()
    assert result == "test_result"
    assert cached is False
    assert mock_func.call_count == 1

    # Second call, should be cached
    result, cached = cached_func()
    assert result == "test_result"
    assert cached is True
    assert mock_func.call_count == 1  # Should not be called again

    # Wait for cache to expire
    import time

    time.sleep(1.1)

    # Third call, should not be cached
    result, cached = cached_func()
    assert result == "test_result"
    assert cached is False
    assert mock_func.call_count == 2


@patch("sesame_exporter._impl.time.sleep")  # Mock sleep for backoff
def test_update_metrics(mock_sleep, mock_get):
    # Mock the API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "batteryVoltage": 3.0,
        "batteryPercentage": 50,
        "success": True,
    }
    mock_get.return_value = mock_response

    # Mock Gauges
    mock_voltage_gauge = MagicMock()
    mock_percent_gauge = MagicMock()

    with patch.dict(
        sesame._METRICS_KEYS,
        {
            "batteryVoltage": mock_voltage_gauge,
            "batteryPercentage": mock_percent_gauge,
        },
        clear=True,
    ):
        uuids = {"HOME_FRONT": "uuid1"}
        sesame.update_metrics(uuids, "api_key")

    # Verify calls
    mock_voltage_gauge.labels.assert_called_with(device="HOME_FRONT")
    mock_percent_gauge.labels.assert_called_with(device="HOME_FRONT")
    mock_voltage_gauge.labels.return_value.set.assert_called_with(3.0)
    mock_percent_gauge.labels.return_value.set.assert_called_with(50.0)


def test_parse_args_defaults():
    with patch("sys.argv", ["sesame.py"]):
        args = _parse_args()
        assert args.port == 8000
        assert args.sesame_uuids == {}


def test_parse_args_cli():
    with patch(
        "sys.argv",
        [
            "sesame.py",
            "--port",
            "9090",
            "--sesame-uuid",
            "Door=1234",
            "--sesame-uuid",
            "Gate=5678",
        ],
    ):
        args = _parse_args()
        assert args.port == 9090
        assert args.sesame_uuids == {"Door": "1234", "Gate": "5678"}


def test_parse_args_config_file(tmp_path):
    config_file = tmp_path / "sesame.yaml"
    config_data = {"port": 7000, "sesame_uuids": {"ConfigDoor": "9999"}}
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    with patch("sys.argv", ["sesame.py", "--config", str(config_file)]):
        args = _parse_args()
        assert args.port == 7000
        assert args.sesame_uuids == {"ConfigDoor": "9999"}


def test_parse_args_override(tmp_path):
    config_file = tmp_path / "sesame.yaml"
    config_data = {
        "port": 7000,
        "sesame_uuids": {"ConfigDoor": "9999", "OverrideMe": "Old"},
    }
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    # CLI overrides port and updates/adds UUIDs
    with patch(
        "sys.argv",
        [
            "sesame.py",
            "--config",
            str(config_file),
            "--port",
            "8080",
            "--sesame-uuid",
            "OverrideMe=New",
            "--sesame-uuid",
            "New=1111",
        ],
    ):
        args = _parse_args()
        assert args.port == 8080
        assert args.sesame_uuids["ConfigDoor"] == "9999"
        assert args.sesame_uuids["OverrideMe"] == "New"
        assert args.sesame_uuids["New"] == "1111"
