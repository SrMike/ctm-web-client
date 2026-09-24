"""
Consulta el estado actual de reportId's ya generados anteriormente,
sin volver a ejecutar el reporte. Util para saber si un reporte que
se quedo "PROCESSING" en un intento previo ya termino en el servidor.

Uso:
    python check_report_status.py <report_id> [<report_id> ...]
"""
import argparse
import json
import os
import sys
from datetime import datetime
from getpass import getpass
from pathlib import Path

from ctm_web_client import ControlMWebClient
from ctm_web_client.exceptions import ControlMWebError

ENV_FILE = Path(".env")


class Tee:
    """Duplica la salida estandar hacia consola y hacia un archivo de log."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for stream in self._streams:
            stream.write(data)
            stream.flush()

    def flush(self):
        for stream in self._streams:
            stream.flush()


def load_dotenv(path: Path = ENV_FILE) -> None:
    """Carga variables desde un archivo .env sin sobrescribir las ya definidas
    en el entorno real. No requiere dependencias externas."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Consulta estado de reportId's")
    parser.add_argument("report_ids", nargs="+", help="Uno o mas reportId a consultar")
    parser.add_argument("--base-url", default=os.environ.get("CTM_BASE_URL", ""))
    parser.add_argument("--username", default=os.environ.get("CTM_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("CTM_PASSWORD", ""))
    parser.add_argument("--verify-ssl", action="store_true", default=False)
    parser.add_argument("--log-file", default=None, help="Ruta del archivo de log (por defecto se genera con fecha/hora)")
    args = parser.parse_args()

    base_url = args.base_url or input("Base URL: ")
    username = args.username or input("Usuario: ")
    password = args.password or getpass("Password: ")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path(args.log_file or f"check_report_status_{timestamp}_log.txt")
    log_file = open(log_path, "w", encoding="utf-8")
    original_stdout = sys.stdout
    sys.stdout = Tee(original_stdout, log_file)

    try:
        _check(base_url, username, password, args.verify_ssl, args.report_ids)
    finally:
        sys.stdout = original_stdout
        log_file.close()
        print(f"Log guardado en: {log_path}")


def _check(base_url: str, username: str, password: str, verify_ssl: bool, report_ids) -> None:
    with ControlMWebClient(base_url, verify_ssl=verify_ssl, timeout=30) as client:
        client.login(username, password)
        print("Login OK\n")

        for report_id in report_ids:
            print("=" * 60)
            print(f"report_id={report_id}")
            print("=" * 60)
            try:
                status = client.get_report_status(report_id)
                print(json.dumps(status, indent=2, ensure_ascii=False))

                if status.get("status") == "SUCCEEDED":
                    report_format = (status.get("format") or "csv").lower()
                    content = client.download_report({"reportId": report_id})
                    output_path = Path(f"reporte_{report_id}.{report_format}")
                    output_path.write_bytes(content)
                    print(f"  Descargado: {output_path} ({len(content)} bytes)")
            except ControlMWebError as exc:
                print(f"ERROR: {exc}")
            print()


if __name__ == "__main__":
    main()
