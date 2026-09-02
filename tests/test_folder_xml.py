"""Pruebas sin red para la descarga XML nativa de folders."""

from pathlib import Path

import pytest

from ctm_web_client import ControlMDownloader, ControlMWebClient
from ctm_web_client.exceptions import ControlMWebError, ExportError

FOLDER = "FOLDER_EXAMPLE"
SERVER = "CTM_EXAMPLE"
VALID_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<DEFTABLE><FOLDER FOLDER_NAME="FOLDER_EXAMPLE">'
    b'<JOB JOBNAME="JOB_EXAMPLE"/></FOLDER></DEFTABLE>'
)


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        status_code: int = 200,
        content_type: str = "application/json",
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = {"content-type": content_type}


def make_client(response: FakeResponse) -> tuple[ControlMWebClient, list]:
    client = object.__new__(ControlMWebClient)
    calls = []

    def fake_api_get(path: str, **kwargs):
        calls.append((path, kwargs))
        return response

    client._api_get = fake_api_get
    return client, calls


def test_get_folder_definition_xml_returns_original_bytes_and_uses_params() -> None:
    client, calls = make_client(FakeResponse(VALID_XML))

    result = client.get_folder_definition_xml(f" {FOLDER} ", f" {SERVER} ")

    assert result is VALID_XML
    assert calls == [
        (
            "deploy/jobs",
            {
                "params": {
                    "format": "xml",
                    "folder": FOLDER,
                    "ctm": SERVER,
                    "useArrayFormat": "false",
                }
            },
        )
    ]


@pytest.mark.parametrize("folder, server", [("", SERVER), (FOLDER, ""), ("   ", SERVER)])
def test_get_folder_definition_xml_rejects_empty_parameters(
    folder: str,
    server: str,
) -> None:
    client, _ = make_client(FakeResponse(VALID_XML))

    with pytest.raises(ValueError):
        client.get_folder_definition_xml(folder, server)


@pytest.mark.parametrize(
    "content, message",
    [
        (b'{"errors": []}', "no devolvió XML válido"),
        (b"<OTHER/>", "Raíz XML inesperada"),
        (b"<DEFTABLE/>", "contiene 0 folders"),
        (
            b'<DEFTABLE><FOLDER FOLDER_NAME="OTHER"/></DEFTABLE>',
            "contiene 0 folders",
        ),
        (
            b'<DEFTABLE><FOLDER FOLDER_NAME="FOLDER_EXAMPLE"/>'
            b'<FOLDER FOLDER_NAME="FOLDER_EXAMPLE"/></DEFTABLE>',
            "contiene 2 folders",
        ),
    ],
)
def test_get_folder_definition_xml_rejects_invalid_content(
    content: bytes,
    message: str,
) -> None:
    client, _ = make_client(FakeResponse(content))

    with pytest.raises(ControlMWebError, match=message):
        client.get_folder_definition_xml(FOLDER, SERVER)


def test_get_folder_definition_xml_rejects_http_error() -> None:
    client, _ = make_client(FakeResponse(b"forbidden", status_code=403))

    with pytest.raises(ControlMWebError, match="HTTP 403"):
        client.get_folder_definition_xml(FOLDER, SERVER)


class FakeFolderClient:
    def get_folder_definition_xml(self, folder: str, ctm_server: str) -> bytes:
        assert folder == FOLDER
        assert ctm_server == SERVER
        return VALID_XML


def make_downloader(output_dir: Path) -> ControlMDownloader:
    downloader = object.__new__(ControlMDownloader)
    downloader.output_dir = str(output_dir)
    downloader.client = FakeFolderClient()
    return downloader


def test_downloader_saves_default_path_atomically(tmp_path: Path) -> None:
    downloader = make_downloader(tmp_path)

    result = Path(downloader.download_folder_definition_xml(FOLDER, SERVER))

    assert result == (tmp_path / "folder_definitions" / f"{FOLDER}.xml").resolve()
    assert result.read_bytes() == VALID_XML
    assert not Path(f"{result}.part").exists()


def test_downloader_supports_custom_path(tmp_path: Path) -> None:
    downloader = make_downloader(tmp_path)
    output_path = tmp_path / "custom" / "definition.xml"

    result = Path(
        downloader.download_folder_definition_xml(
            FOLDER,
            SERVER,
            output_path=str(output_path),
        )
    )

    assert result == output_path.resolve()
    assert result.read_bytes() == VALID_XML


def test_downloader_removes_partial_file_if_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    downloader = make_downloader(tmp_path)
    output_path = tmp_path / "definition.xml"

    def fail_replace(*_args: str) -> None:
        del _args
        raise OSError("replace failed")

    monkeypatch.setattr("ctm_web_client.downloader.os.replace", fail_replace)

    with pytest.raises(ExportError, match="Error guardando"):
        downloader.download_folder_definition_xml(
            FOLDER,
            SERVER,
            output_path=str(output_path),
        )

    assert not Path(f"{output_path.resolve()}.part").exists()
    assert not output_path.exists()
