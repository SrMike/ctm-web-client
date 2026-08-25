"""
ctm_web_client - Biblioteca para extraer reportes y logs de Control-M/EM Web
sin necesidad de acceso al API oficial.

Uso básico:
    from ctm_web_client import ControlMWebClient

    client = ControlMWebClient("https://controlm-server:8443/ControlM")
    client.login("usuario", "contraseña")

    # Obtener jobs ejecutados
    jobs = client.get_jobs(folder="MI_FOLDER", date="2026-08-20")

    # Descargar log de un job
    log = client.get_job_log(job_id="SERVER:00abc")

    # Exportar reporte
    client.export_report("ejecuciones", format="csv", output_path="reporte.csv")

    client.logout()
"""

from ctm_web_client.client_v2 import ControlMWebClient
from ctm_web_client.exporters import JSONExporter, CSVExporter, TextExporter
from ctm_web_client.proto_decoder import decode_em_response, decode_nested, decode_strings

__version__ = "2.0.2"
__all__ = [
    "ControlMWebClient",
    "JSONExporter", "CSVExporter", "TextExporter",
    "decode_em_response", "decode_nested", "decode_strings",
]
