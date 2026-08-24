"""
Ejemplo de uso de ctm_web_client.

Ajusta BASE_URL, USERNAME y PASSWORD antes de ejecutar.
"""

import json
import os

from ctm_web_client import ControlMWebClient, decode_nested
from ctm_web_client.exporters import CSVExporter, JSONExporter, TextExporter

# ─── Configuracion ────────────────────────────────────────────────────────────
BASE_URL = "https://tu-servidor-controlm:8443/ControlM"
USERNAME = "tu_usuario"
PASSWORD = os.environ.get("CTM_PASSWORD", "tu_password")
VERIFY_SSL = False
# ──────────────────────────────────────────────────────────────────────────────


def main():
    with ControlMWebClient(BASE_URL, verify_ssl=VERIFY_SSL) as client:
        client.login(USERNAME, PASSWORD)

        # 1. Jobs activos con error
        print("=== JOBS CON ERROR ===")
        failed_jobs = client.get_jobs(status="Ended Not OK", limit=50)
        for j in failed_jobs[:10]:
            print(f"  {j.get('jobId')} | {j.get('name')} | {j.get('folder')}")

        # 2. Descargar log y output de un job
        if failed_jobs:
            job_id = failed_jobs[0].get("jobId", "")
            print(f"\n=== LOG DE {job_id} ===")
            log = client.get_job_log(job_id)
            print(log[:500])

            print(f"\n=== OUTPUT DE {job_id} ===")
            output = client.get_job_output(job_id)
            print(output[:500])

        # 3. Ejecutar reporte desde .em.json
        print("\n=== EJECUTAR REPORTE ===")
        with open("mi_reporte.em.json", "r") as f:
            config = json.load(f)

        csv_bytes = client.wait_and_download_report(config["reportName"], config)
        with open("resultado.csv", "wb") as f:
            f.write(csv_bytes)
        print(f"  Descargado: resultado.csv ({len(csv_bytes):,} bytes)")

        # 4. Servidores
        print("\n=== SERVIDORES ===")
        servers = client.get_servers()
        for s in servers:
            print(f"  {s.get('name')} | {s.get('host')} | {s.get('state')}")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
