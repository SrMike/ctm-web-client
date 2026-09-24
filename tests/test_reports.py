"""Pruebas sin red para la ejecución y descarga de reportes."""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from ctm_web_client import ControlMDownloader, ControlMWebClient
from ctm_web_client.exceptions import ControlMWebError

# Fechas de prueba: ayer y hoy
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
DATE_RANGE = f"{YESTERDAY.strftime('%Y-%m-%d')}%{TODAY.strftime('%Y-%m-%d')}"

REPORT_NAME = "EJEC_CON_ESTADO_MX_*"
REPORT_ID = "report-execution-12345"


class FakeResponse:
    def __init__(
        self,
        content: bytes | dict | str,
        status_code: int = 200,
        content_type: str = "application/json",
    ) -> None:
        if isinstance(content, dict):
            self.content = json.dumps(content).encode("utf-8")
            self.text = json.dumps(content)
            self.json_data = content
        elif isinstance(content, str):
            self.content = content.encode("utf-8")
            self.text = content
            self.json_data = None
        else:
            self.content = content
            self.text = content.decode("utf-8", errors="ignore")
            self.json_data = None

        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def json(self):
        if self.json_data is not None:
            return self.json_data
        return json.loads(self.text)


def make_client(
    responses: dict[str, FakeResponse],
) -> tuple[ControlMWebClient, list]:
    """Crea un cliente simulado que devuelve respuestas predefinidas."""
    client = object.__new__(ControlMWebClient)
    calls = []

    def fake_api_get(path: str, **kwargs):
        calls.append(("GET", path, kwargs))
        if path in responses:
            return responses[path]
        raise KeyError(f"No response configured for GET {path}")

    def fake_api_post(path: str, json_data: dict = None, **kwargs):
        calls.append(("POST", path, json_data or {}, kwargs))
        key = f"POST:{path}"
        if key in responses:
            return responses[key]
        raise KeyError(f"No response configured for POST {path}")

    class FakeSession:
        """Simula requests.Session() para download_report(), que llama
        directamente a self._session.get() en lugar de _api_get()."""

        def get(self, url: str, headers=None, verify=None, timeout=None):
            calls.append(("SESSION_GET", url, headers or {}))
            for key, response in responses.items():
                if key in url:
                    return response
            raise KeyError(f"No response configured for session GET {url}")

    client._api_get = fake_api_get
    client._api_post = fake_api_post
    client._session = FakeSession()
    client._authenticated = True
    client.base_url = "https://controlm.example:8443/ControlM"
    client._em_token = "fake-token"
    client.verify_ssl = True
    client.timeout = 30
    return client, calls


def test_run_report_with_config_returns_report_id() -> None:
    """Valida que run_report() inicia la ejecución y devuelve reportId."""
    execution_response = FakeResponse(
        {
            "reportId": REPORT_ID,
            "status": "RUNNING",
            "reportName": REPORT_NAME,
            "timestamp": "2026-09-21T10:00:00Z",
        }
    )
    responses = {"POST:reporting/report": execution_response}
    client, calls = make_client(responses)

    result = client.run_report(
        REPORT_NAME,
        {"format": "CSV", "userData": {"userFilters": []}},
    )

    assert result.get("reportId") == REPORT_ID
    assert result.get("status") == "RUNNING"
    assert len(calls) == 1
    assert calls[0][0] == "POST"
    assert calls[0][1] == "reporting/report"


def test_run_report_from_file_with_real_em_json() -> None:
    """Valida que run_report_from_file() carga y ejecuta un .em.json real."""
    em_json_path = Path(__file__).resolve().parent.parent / "EJEC_CON_ESTADO_MX__TEMP.em.json"

    if not em_json_path.exists():
        pytest.skip(f"Template file not found: {em_json_path}")

    with open(em_json_path, "r", encoding="utf-8") as f:
        template = json.load(f)

    # Actualizar fechas a ayer y hoy
    for filter_item in template["userData"]["userFilters"]:
        if filter_item["columnId"] == "START_DATE_IDX":
            filter_item["value"] = DATE_RANGE

    execution_response = FakeResponse(
        {
            "reportId": REPORT_ID,
            "status": "RUNNING",
            "reportName": template["reportName"],
        }
    )
    responses = {"POST:reporting/report": execution_response}
    client, calls = make_client(responses)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_em_json = Path(tmpdir) / "temp_report.em.json"
        with open(temp_em_json, "w", encoding="utf-8") as f:
            json.dump(template, f)

        result = client.run_report_from_file(
            str(temp_em_json),
            output_format="CSV",
        )

    assert result.get("reportId") == REPORT_ID
    assert len(calls) == 1


def test_get_report_status_returns_state() -> None:
    """Valida que get_report_status() consulta el estado de ejecución."""
    status_response = FakeResponse(
        {
            "reportId": REPORT_ID,
            "status": "COMPLETED",
            "timestamp": "2026-09-21T10:05:00Z",
        }
    )
    responses = {f"reporting/status/{REPORT_ID}": status_response}
    client, calls = make_client(responses)

    status = client.get_report_status(REPORT_ID)

    assert status.get("status") == "COMPLETED"
    assert status.get("reportId") == REPORT_ID


def test_download_report_returns_bytes() -> None:
    """Valida que download_report() retorna bytes del archivo."""
    csv_content = b"ORDER_ID,JOB_NAME,STATUS\n1001,JOB_A,OK\n1002,JOB_B,NOT OK\n"
    download_response = FakeResponse(
        csv_content,
        content_type="text/csv",
    )
    responses = {"reporting/download": download_response}
    client, calls = make_client(responses)

    result = client.download_report({"reportId": REPORT_ID})

    assert result == csv_content
    assert isinstance(result, bytes)


def test_wait_and_download_report_polls_and_downloads() -> None:
    """Valida que wait_and_download_report() ejecuta, espera y descarga."""
    execution_response = FakeResponse(
        {
            "reportId": REPORT_ID,
            "status": "RUNNING",
        }
    )
    status_response_running = FakeResponse(
        {
            "reportId": REPORT_ID,
            "status": "RUNNING",
        }
    )
    status_response_completed = FakeResponse(
        {
            "reportId": REPORT_ID,
            "status": "COMPLETED",
        }
    )
    csv_content = b"ORDER_ID,JOB_NAME,STATUS\n1001,JOB_A,OK\n"
    download_response = FakeResponse(
        csv_content,
        content_type="text/csv",
    )

    responses = {
        "POST:reporting/report": execution_response,
        f"reporting/status/{REPORT_ID}": status_response_completed,
        "reporting/download": download_response,
    }
    client, calls = make_client(responses)

    result = client.wait_and_download_report(
        REPORT_NAME,
        {"userData": {"userFilters": []}},
        output_format="CSV",
        poll_interval=0.1,  # Muy rápido para pruebas
        max_wait=5,
    )

    assert result == csv_content
    assert len(calls) >= 2  # Al menos POST y GET status y download


def test_wait_and_download_report_timeout() -> None:
    """Valida que wait_and_download_report() falla con timeout."""
    execution_response = FakeResponse(
        {
            "reportId": REPORT_ID,
            "status": "RUNNING",
        }
    )
    status_response_running = FakeResponse(
        {
            "reportId": REPORT_ID,
            "status": "RUNNING",
        }
    )

    responses = {
        "POST:reporting/report": execution_response,
        f"reporting/status/{REPORT_ID}": status_response_running,
    }
    client, calls = make_client(responses)

    with pytest.raises(ControlMWebError, match="(?i)timeout|tiempo agotado"):
        client.wait_and_download_report(
            REPORT_NAME,
            {"userData": {"userFilters": []}},
            output_format="CSV",
            poll_interval=0.1,
            max_wait=0.2,  # Muy corto para forzar timeout
        )


def test_wait_and_download_report_handles_error_status() -> None:
    """Valida que wait_and_download_report() maneja estados de error."""
    execution_response = FakeResponse(
        {
            "reportId": REPORT_ID,
            "status": "RUNNING",
        }
    )
    status_response_failed = FakeResponse(
        {
            "reportId": REPORT_ID,
            "status": "FAILED",
            "error": "Insufficient permissions",
        }
    )

    responses = {
        "POST:reporting/report": execution_response,
        f"reporting/status/{REPORT_ID}": status_response_failed,
    }
    client, calls = make_client(responses)

    with pytest.raises(ControlMWebError, match="FAILED|error"):
        client.wait_and_download_report(
            REPORT_NAME,
            {"userData": {"userFilters": []}},
            output_format="CSV",
            poll_interval=0.1,
            max_wait=5,
        )


def test_downloader_download_report_integration() -> None:
    """Valida que ControlMDownloader.download_report() exporta la respuesta
    de ejecución del reporte a un archivo, saneando nombres con caracteres
    especiales (p. ej. '*' en REPORT_NAME) para que la ruta sea válida."""
    execution_response = FakeResponse(
        {
            "reportId": REPORT_ID,
            "status": "RUNNING",
        }
    )

    responses = {"POST:reporting/report": execution_response}
    client, _ = make_client(responses)

    downloader = object.__new__(ControlMDownloader)
    downloader.client = client
    downloader.output_dir = Path(tempfile.mkdtemp())

    result_path = downloader.download_report(
        REPORT_NAME,
        params={"format": "CSV"},
        format="json",
    )

    assert result_path
    assert Path(result_path).exists()
    with open(result_path, "r") as f:
        content = f.read()
    assert REPORT_ID in content
    assert "RUNNING" in content


def test_report_template_structure() -> None:
    """Valida la estructura del archivo .em.json de prueba."""
    em_json_path = Path(__file__).resolve().parent.parent / "EJEC_CON_ESTADO_MX__TEMP.em.json"

    if not em_json_path.exists():
        pytest.skip(f"Template file not found: {em_json_path}")

    with open(em_json_path, "r", encoding="utf-8") as f:
        template = json.load(f)

    assert template.get("reportName")
    assert template.get("userData")
    assert template["userData"].get("userFilters")
    assert template["userData"].get("userColumns")
    assert template["userData"].get("userGeneralConfigurations")

    # Verificar que hay un filtro START_DATE_IDX para fechas
    has_date_filter = any(
        f["columnId"] == "START_DATE_IDX"
        for f in template["userData"]["userFilters"]
    )
    assert has_date_filter, "Template debe tener filtro START_DATE_IDX"
