"""
Prueba: descarga (exporta) TODOS los reportes guardados de la cuenta como
archivos .em.json individuales, replicando el shape del boton "Export" de
la UI de Control-M Web (Reports).

Contexto: se confirmo (test_rf_server_fix_20260923_140952.txt) que
get_report_metadata() (POST /RF-Server/report/loadReportMetadata) ya
devuelve, entre otras claves, un campo 'userData' calculado por el propio
servidor. Los archivos .em.json reales exportados desde la UI (ver
'Jobs Definitions_1.em.json' en la raiz del repo) tienen exactamente este
shape compacto:
    {reportName, description, userData, categoryId, reportDesignName,
     templateId}
Por eso este script NO reconstruye 'userData' a mano (evita adivinar): lo
toma tal cual lo devuelve el servidor para cada reporte, y descarta el
resto de las claves (reportId, columns, filters, fieldMapper,
dateTimeSettings, etc.) que loadReportMetadata agrega pero que el archivo
.em.json exportado no incluye.

Este script:
    1. Lista todos los reportes guardados (getAllUserReports).
    2. Para cada uno, llama get_report_metadata() con los campos de
       origen (categoryId/reportDesignName/templateId) para evitar el
       500 documentado cuando faltan.
    3. Guarda cada resultado recortado como '<nombre_sanitizado>.em.json'
       dentro de em_json_export/.
    4. Reporta exitos y fallos (algunos reportes pueden fallar si tienen
       filtros obligatorios no satisfechos por defaults vacios).

Sigue el protocolo obligatorio de discovery/session_state.py: guarda el
estado de sesion tras el login y garantiza logout en finally. Guarda toda
la salida en discovery/export_all_reports_em_json_<timestamp>.txt.

Uso:
    python export_all_reports_em_json.py

Lee CTM_BASE_URL, CTM_USERNAME y CTM_PASSWORD desde el .env de la raiz del
repo. Si CTM_PASSWORD no esta definida, se pide de forma oculta con
getpass().
"""

import json
import os
import re
import sys
import warnings
from datetime import datetime
from getpass import getpass
from pathlib import Path

warnings.filterwarnings("ignore")
try:
    import urllib3
    urllib3.disable_warnings()
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent / "discovery"))
from session_state import clear_session_state, save_session_state_from_client  # noqa: E402

from ctm_web_client import ControlMWebClient  # noqa: E402
from ctm_web_client.exceptions import ControlMWebError  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / ".env"
EXPORT_DIR = ROOT_DIR / "em_json_export"

# Claves que forman el shape real de un .em.json exportado desde la UI
# (confirmado contra 'Jobs Definitions_1.em.json' ya presente en el repo).
EM_JSON_KEYS = ("reportName", "description", "userData", "categoryId", "reportDesignName", "templateId")


def load_dotenv(path: Path = ENV_FILE) -> None:
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


load_dotenv()
BASE_URL = os.environ.get("CTM_BASE_URL") or input("Base URL (https://host:8443/ControlM): ").strip()
USERNAME = os.environ.get("CTM_USERNAME") or input("Usuario: ").strip()
PASSWORD = os.environ.get("CTM_PASSWORD") or getpass("Password: ")

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = ROOT_DIR / "discovery" / f"export_all_reports_em_json_{TIMESTAMP}.txt"

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]')


def sanitize_filename(name: str) -> str:
    return _UNSAFE_CHARS.sub("_", name).strip() or "reporte_sin_nombre"


class Logger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.path, "w", encoding="utf-8")
        self.section("PRUEBA: exportar todos los reportes como .em.json")
        self.log(f"Fecha: {datetime.now().isoformat()}")

    def log(self, msg=""):
        text = str(msg)
        print(text)
        self._handle.write(text + "\n")
        self._handle.flush()

    def section(self, title):
        self.log(f"\n{'=' * 70}\n  {title}\n{'=' * 70}")

    def close(self):
        self.log(f"\nLog guardado en: {self.path}")
        self._handle.close()


def main() -> None:
    logger = Logger(LOG_FILE)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    client = ControlMWebClient(BASE_URL, verify_ssl=False, timeout=30)
    try:
        logger.log(f"Login como {USERNAME!r} en {BASE_URL} ...")
        client.login(USERNAME, PASSWORD)
        logger.log(f"is_authenticated = {client.is_authenticated}")

        save_session_state_from_client(client)
        logger.log("Estado de sesion guardado localmente (discovery/.session_state.json).")

        logger.section("Catalogo de reportes (getAllUserReports)")
        reports = client.list_saved_reports()
        logger.log(f"Total reportes encontrados: {len(reports)}")

        ok_count = 0
        fail_count = 0
        used_names = set()

        logger.section("Exportando cada reporte a .em.json")
        for entry in reports:
            report_name = entry.get("reportName", "")
            report_id = entry.get("reportId", "")
            try:
                metadata = client.get_report_metadata(
                    report_name,
                    description=entry.get("description", ""),
                    category_id=entry.get("categoryId"),
                    report_design_name=entry.get("reportDesignName"),
                    template_id=entry.get("templateId"),
                )
                em_json = {k: metadata.get(k) for k in EM_JSON_KEYS}

                base_filename = sanitize_filename(report_name)
                filename = f"{base_filename}.em.json"
                suffix = 2
                while filename in used_names:
                    filename = f"{base_filename}_{suffix}.em.json"
                    suffix += 1
                used_names.add(filename)

                output_path = EXPORT_DIR / filename
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(em_json, f, ensure_ascii=False)

                logger.log(f"  OK  [{report_id}] '{report_name}' -> em_json_export/{filename}")
                ok_count += 1
            except ControlMWebError as exc:
                logger.log(f"  FALLO [{report_id}] '{report_name}': {exc}")
                fail_count += 1
            except Exception as exc:
                logger.log(f"  FALLO [{report_id}] '{report_name}' (error inesperado): {exc}")
                fail_count += 1

        logger.section("Resumen")
        logger.log(f"Total reportes: {len(reports)}")
        logger.log(f"Exportados OK: {ok_count}")
        logger.log(f"Fallidos: {fail_count}")
        logger.log(f"Carpeta de salida: {EXPORT_DIR}")

    finally:
        try:
            client.logout()
            logger.log("\nLogout realizado.")
        except Exception as exc:
            logger.log(f"\nERROR en logout: {exc}")
        clear_session_state()
        logger.close()


if __name__ == "__main__":
    main()
