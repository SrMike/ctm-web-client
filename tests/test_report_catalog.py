"""Pruebas sin red para el catálogo de reportes guardados (RF-Server).

Cubre list_saved_reports(), get_report_metadata(), validate_report_name(),
create_report(), save_report_as(), create_report_from_file() y
delete_report(). No usa credenciales, URLs ni nombres de usuario reales:
todos los datos son ficticios y los archivos .em.json se generan en
directorios temporales dentro de cada prueba.
"""

import json
import tempfile
from pathlib import Path

import pytest

from ctm_web_client import ControlMWebClient
from ctm_web_client.exceptions import ControlMWebError

# Datos de prueba genéricos (no reales).
FAKE_USERNAME = "test_user"
SOURCE_REPORT_NAME = "Report A"
SOURCE_REPORT_ID = "11111111-1111-1111-1111-111111111111"
NEW_REPORT_ID = "22222222-2222-2222-2222-222222222222"


class FakeResponse:
    def __init__(self, content) -> None:
        self._content = content

    def json(self):
        return self._content


def make_client(rf_get=None, rf_post=None, rf_delete=None):
    """Crea un ControlMWebClient simulado, sustituyendo las llamadas HTTP
    internas del motor RF-Server por callables de prueba."""
    client = object.__new__(ControlMWebClient)
    client._username = FAKE_USERNAME
    calls = []

    def default_get(path, **kwargs):
        raise KeyError(f"No hay respuesta configurada para GET {path}")

    def default_post(path, json_body=None, **kwargs):
        raise KeyError(f"No hay respuesta configurada para POST {path}")

    def default_delete(path, params=None, **kwargs):
        raise KeyError(f"No hay respuesta configurada para DELETE {path}")

    def wrapped_get(path, **kwargs):
        calls.append(("GET", path, kwargs))
        return (rf_get or default_get)(path, **kwargs)

    def wrapped_post(path, json_body=None, **kwargs):
        calls.append(("POST", path, json_body, kwargs))
        return (rf_post or default_post)(path, json_body=json_body, **kwargs)

    def wrapped_delete(path, params=None, **kwargs):
        calls.append(("DELETE", path, params, kwargs))
        return (rf_delete or default_delete)(path, params=params, **kwargs)

    client._rf_server_get = wrapped_get
    client._rf_server_post = wrapped_post
    client._rf_server_delete = wrapped_delete
    return client, calls


def make_source_report_entry() -> dict:
    return {
        "reportId": SOURCE_REPORT_ID,
        "reportName": SOURCE_REPORT_NAME,
        "description": "Reporte de origen de prueba",
        "categoryId": "1",
        "reportDesignName": "fake-design.rptdesign",
        "templateId": 1,
    }


def make_source_metadata(columns=None) -> dict:
    entry = make_source_report_entry()
    entry["columns"] = columns if columns is not None else [{"columnId": "FAKE_COLUMN"}]
    entry["userData"] = {
        "userSorts": [],
        "userGroups": [],
        "userFilters": [],
        "userColumns": [{"columnId": "FAKE_COLUMN"}],
        "userGeneralConfigurations": {
            "allowedFormats": ["PDF", "CSV", "EXCEL"],
            "isPreviewAllowed": True,
        },
    }
    return entry


# ── list_saved_reports() ────────────────────────────────────────────────

def test_list_saved_reports_returns_catalog() -> None:
    catalog = [make_source_report_entry()]

    def rf_get(path, **kwargs):
        assert path == "report/getAllUserReports"
        return FakeResponse(catalog)

    client, calls = make_client(rf_get=rf_get)

    result = client.list_saved_reports()

    assert result == catalog
    assert calls == [("GET", "report/getAllUserReports", {})]


# ── get_report_metadata() ───────────────────────────────────────────────

def test_get_report_metadata_sends_required_top_level_fields() -> None:
    metadata = make_source_metadata()

    def rf_post(path, json_body=None, **kwargs):
        assert path == "report/loadReportMetadata"
        # Campos que, si faltan, el servidor real responde HTTP 500 vacío.
        assert json_body["categoryId"] == "1"
        assert json_body["reportDesignName"] == "fake-design.rptdesign"
        assert json_body["templateId"] == 1
        assert "userColumns" in json_body["userData"]
        assert "userGeneralConfigurations" in json_body["userData"]
        return FakeResponse(metadata)

    client, calls = make_client(rf_post=rf_post)

    result = client.get_report_metadata(
        SOURCE_REPORT_NAME,
        category_id="1",
        report_design_name="fake-design.rptdesign",
        template_id=1,
    )

    assert result == metadata
    assert len(calls) == 1


# ── validate_report_name() ──────────────────────────────────────────────

def test_validate_report_name_returns_bool() -> None:
    def rf_post(path, json_body=None, **kwargs):
        assert path == "report/validateReport"
        return FakeResponse(True)

    client, _ = make_client(rf_post=rf_post)

    assert client.validate_report_name("Nuevo Reporte") is True


# ── create_report() ─────────────────────────────────────────────────────

def test_create_report_defaults_report_id_and_username() -> None:
    captured = {}

    def rf_post(path, json_body=None, **kwargs):
        assert path == "report/addNewReport"
        captured.update(json_body)
        return FakeResponse({**json_body, "reportId": NEW_REPORT_ID})

    client, _ = make_client(rf_post=rf_post)

    result = client.create_report({"reportName": "Reporte sin id"})

    assert captured["reportId"] == "NEW_REPORT"
    assert captured["userName"] == FAKE_USERNAME
    assert result["reportId"] == NEW_REPORT_ID


def test_create_report_respects_explicit_report_id_and_username() -> None:
    captured = {}

    def rf_post(path, json_body=None, **kwargs):
        captured.update(json_body)
        return FakeResponse(json_body)

    client, _ = make_client(rf_post=rf_post)

    client.create_report({
        "reportName": "Reporte con id",
        "reportId": "ya-existe",
        "userName": "otro_usuario",
    })

    assert captured["reportId"] == "ya-existe"
    assert captured["userName"] == "otro_usuario"


# ── save_report_as() ─────────────────────────────────────────────────────

def test_save_report_as_builds_copy_from_source() -> None:
    catalog = [make_source_report_entry()]
    metadata = make_source_metadata()

    def rf_get(path, **kwargs):
        return FakeResponse(catalog)

    def rf_post(path, json_body=None, **kwargs):
        if path == "report/loadReportMetadata":
            return FakeResponse(metadata)
        if path == "report/addNewReport":
            assert json_body["reportName"] == "Report A - Copia"
            assert json_body["reportId"] == "NEW_REPORT"
            assert json_body["columns"] == metadata["columns"]
            return FakeResponse({**json_body, "reportId": NEW_REPORT_ID})
        raise AssertionError(f"Ruta POST inesperada: {path}")

    client, _ = make_client(rf_get=rf_get, rf_post=rf_post)

    result = client.save_report_as(SOURCE_REPORT_NAME, "Report A - Copia")

    assert result["reportId"] == NEW_REPORT_ID
    assert result["reportName"] == "Report A - Copia"


def test_save_report_as_raises_when_source_missing() -> None:
    def rf_get(path, **kwargs):
        return FakeResponse([])  # catálogo vacío

    client, _ = make_client(rf_get=rf_get)

    with pytest.raises(ControlMWebError, match="no encontrado"):
        client.save_report_as("Reporte inexistente", "Copia")


# ── create_report_from_file() ───────────────────────────────────────────

def write_temp_em_json(tmp_path: Path, data: dict) -> Path:
    em_json_path = tmp_path / "reporte_prueba.em.json"
    with open(em_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return em_json_path


def test_create_report_from_file_uses_file_report_name_as_source(tmp_path) -> None:
    catalog = [make_source_report_entry()]
    metadata = make_source_metadata()
    em_json_path = write_temp_em_json(tmp_path, {
        "reportName": SOURCE_REPORT_NAME,
        "description": "Descripcion editada desde archivo",
        "userData": {"userSorts": [], "userGroups": [], "userFilters": [{"columnId": "X", "operator": "Equal", "value": "1"}]},
        "categoryId": "1",
        "reportDesignName": "fake-design.rptdesign",
        "templateId": 1,
    })

    def rf_get(path, **kwargs):
        return FakeResponse(catalog)

    def rf_post(path, json_body=None, **kwargs):
        if path == "report/loadReportMetadata":
            return FakeResponse(metadata)
        if path == "report/addNewReport":
            assert json_body["description"] == "Descripcion editada desde archivo"
            assert json_body["userData"]["userFilters"][0]["columnId"] == "X"
            return FakeResponse({**json_body, "reportId": NEW_REPORT_ID})
        raise AssertionError(f"Ruta POST inesperada: {path}")

    client, _ = make_client(rf_get=rf_get, rf_post=rf_post)

    result = client.create_report_from_file(str(em_json_path))

    assert result["reportId"] == NEW_REPORT_ID
    assert result["reportName"] == SOURCE_REPORT_NAME


def test_create_report_from_file_uses_explicit_new_name(tmp_path) -> None:
    catalog = [make_source_report_entry()]
    metadata = make_source_metadata()
    em_json_path = write_temp_em_json(tmp_path, {
        "reportName": SOURCE_REPORT_NAME,
        "userData": {},
        "categoryId": "1",
        "reportDesignName": "fake-design.rptdesign",
        "templateId": 1,
    })

    def rf_get(path, **kwargs):
        return FakeResponse(catalog)

    def rf_post(path, json_body=None, **kwargs):
        if path == "report/loadReportMetadata":
            return FakeResponse(metadata)
        if path == "report/addNewReport":
            assert json_body["reportName"] == "Report A - Prueba"
            return FakeResponse({**json_body, "reportId": NEW_REPORT_ID})
        raise AssertionError(f"Ruta POST inesperada: {path}")

    client, _ = make_client(rf_get=rf_get, rf_post=rf_post)

    result = client.create_report_from_file(
        str(em_json_path),
        new_report_name="Report A - Prueba",
    )

    assert result["reportName"] == "Report A - Prueba"


def test_create_report_from_file_raises_when_source_not_in_catalog(tmp_path) -> None:
    em_json_path = write_temp_em_json(tmp_path, {"reportName": "No existe en catalogo"})

    def rf_get(path, **kwargs):
        return FakeResponse([])  # catálogo vacío

    client, _ = make_client(rf_get=rf_get)

    with pytest.raises(ControlMWebError, match="no encontrado"):
        client.create_report_from_file(str(em_json_path))


def test_create_report_from_file_raises_when_no_report_name_anywhere(tmp_path) -> None:
    em_json_path = write_temp_em_json(tmp_path, {})  # sin 'reportName'

    client, _ = make_client()

    with pytest.raises(ControlMWebError, match="reporte fuente"):
        client.create_report_from_file(str(em_json_path))


# ── delete_report() ──────────────────────────────────────────────────────

def test_delete_report_sends_report_id_in_query_params() -> None:
    def rf_delete(path, params=None, **kwargs):
        assert path == "report/deleteReport"
        assert params == {"report-id": SOURCE_REPORT_ID}
        return FakeResponse("")

    client, calls = make_client(rf_delete=rf_delete)

    client.delete_report(SOURCE_REPORT_ID)

    assert calls == [("DELETE", "report/deleteReport", {"report-id": SOURCE_REPORT_ID}, {})]
