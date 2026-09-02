"""
ctm_web_client - Biblioteca para extraer folders XML, reportes, logs y outputs
de Control-M/EM Web mediante la sesión de la interfaz web.

Uso básico:
    from ctm_web_client import ControlMWebClient

    client = ControlMWebClient("https://controlm-server:8443/ControlM")
    client.login("usuario", "contraseña")

    # Obtener jobs ejecutados
    jobs = client.get_jobs(folder="MI_FOLDER", date="2026-08-20")

    # Descargar log de un job
    log = client.get_job_log(job_id="SERVER:00abc")

    # Descargar un folder completo como XML nativo
    folder_xml = client.get_folder_definition_xml("MI_FOLDER", "CTM_SERVER")

    client.logout()
"""

from ctm_web_client.client_v2 import ControlMWebClient
from ctm_web_client.downloader import ControlMDownloader
from ctm_web_client.exporters import JSONExporter, CSVExporter, TextExporter
from ctm_web_client.proto_decoder import decode_em_response, decode_nested, decode_strings

__version__ = "2.1.0"
__all__ = [
    "ControlMWebClient", "ControlMDownloader",
    "JSONExporter", "CSVExporter", "TextExporter",
    "decode_em_response", "decode_nested", "decode_strings",
]
