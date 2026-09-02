"""
Módulo de alto nivel que combina el cliente con los exportadores
para operaciones comunes de descarga masiva.
"""

import os
import logging
from typing import Optional

from ctm_web_client.client_v2 import ControlMWebClient
from ctm_web_client.exceptions import ExportError
from ctm_web_client.exporters import JSONExporter, CSVExporter, TextExporter

logger = logging.getLogger(__name__)


class ControlMDownloader:
    """
    Clase de alto nivel para folders XML, reportes y logs.

    Combina ControlMWebClient con exportadores para facilitar
    la extracción y guardado de información en lote.

    Ejemplo:
        downloader = ControlMDownloader(
            base_url="https://controlm:8443/ControlM",
            username=os.environ["CTM_USERNAME"],
            password=os.environ["CTM_PASSWORD"],
            output_dir="./descargas"
        )
        downloader.download_all_logs(folder="PRODUCCION", date="2026-08-20")
        downloader.download_folder_definition_xml("PRODUCCION", "CTM_SERVER")
        downloader.download_report("job_status_report", format="csv")
        downloader.close()
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        output_dir: str = "./controlm_output",
        verify_ssl: bool = True,
    ):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        self.client = ControlMWebClient(base_url, verify_ssl=verify_ssl)
        self.client.login(username, password)

    def download_all_logs(
        self,
        folder: Optional[str] = None,
        job_name: Optional[str] = None,
        status: Optional[str] = None,
        date: Optional[str] = None,
    ) -> list[str]:
        """
        Descarga logs de todos los jobs que coincidan con los filtros.

        Returns:
            Lista de rutas de archivos .log creados.
        """
        jobs = self.client.get_jobs(
            folder=folder, job_name=job_name, status=status, date=date
        )
        logger.info(f"Encontrados {len(jobs)} jobs. Descargando logs...")

        logs_dir = os.path.join(self.output_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)

        created_files = []
        for job in jobs:
            job_id = job.get("jobId") or job.get("job_id") or job.get("id")
            job_display = job.get("jobName") or job.get("name") or job_id

            if not job_id:
                continue

            try:
                log_content = self.client.get_job_log(job_id)
                if log_content.strip():
                    filename = f"{job_display}_{job_id.replace(':', '_')}.log"
                    safe_filename = "".join(
                        c if c.isalnum() or c in "._-" else "_" for c in filename
                    )
                    path = TextExporter.export(
                        log_content, os.path.join(logs_dir, safe_filename)
                    )
                    created_files.append(path)
            except Exception as e:
                logger.warning(f"No se pudo descargar log de {job_display}: {e}")

        logger.info(f"Descargados {len(created_files)} logs en {logs_dir}")
        return created_files

    def download_jobs_report(
        self,
        folder: Optional[str] = None,
        status: Optional[str] = None,
        date: Optional[str] = None,
        format: str = "csv",
    ) -> str:
        """
        Genera un reporte de estado de jobs y lo exporta.

        Args:
            format: "csv", "json" o "txt".

        Returns:
            Ruta del archivo generado.
        """
        jobs = self.client.get_jobs(folder=folder, status=status, date=date)

        reports_dir = os.path.join(self.output_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)

        base_name = f"jobs_report_{date or 'all'}"

        if format == "csv":
            path = os.path.join(reports_dir, f"{base_name}.csv")
            return CSVExporter.export(jobs, path)
        elif format == "json":
            path = os.path.join(reports_dir, f"{base_name}.json")
            return JSONExporter.export(jobs, path)
        else:
            path = os.path.join(reports_dir, f"{base_name}.txt")
            content = JSONExporter.to_string(jobs)
            return TextExporter.export(content, path)

    def download_alerts(
        self,
        severity: Optional[str] = None,
        format: str = "csv",
    ) -> str:
        """Descarga alertas y las exporta."""
        alerts = self.client.get_alerts(severity=severity)

        reports_dir = os.path.join(self.output_dir, "alerts")
        os.makedirs(reports_dir, exist_ok=True)

        base_name = f"alerts_{severity or 'all'}"

        if format == "csv":
            path = os.path.join(reports_dir, f"{base_name}.csv")
            return CSVExporter.export(alerts, path)
        else:
            path = os.path.join(reports_dir, f"{base_name}.json")
            return JSONExporter.export(alerts, path)

    def download_history(
        self,
        folder: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        format: str = "csv",
    ) -> str:
        """Descarga historial de ejecuciones."""
        history = self.client.get_history(
            folder=folder, date_from=date_from, date_to=date_to
        )

        reports_dir = os.path.join(self.output_dir, "history")
        os.makedirs(reports_dir, exist_ok=True)

        base_name = f"history_{date_from or 'start'}_{date_to or 'end'}"

        if format == "csv":
            path = os.path.join(reports_dir, f"{base_name}.csv")
            return CSVExporter.export(history, path)
        else:
            path = os.path.join(reports_dir, f"{base_name}.json")
            return JSONExporter.export(history, path)

    def download_report(
        self,
        report_id: str,
        params: Optional[dict] = None,
        format: str = "csv",
    ) -> str:
        """
        Descarga un reporte específico de la sección Reports.

        Args:
            report_id: ID del reporte en Control-M.
            params: Parámetros del reporte.
            format: "csv" o "json".
        """
        data = self.client.get_report_data(report_id, params=params)

        reports_dir = os.path.join(self.output_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)

        if format == "csv":
            path = os.path.join(reports_dir, f"report_{report_id}.csv")
            return CSVExporter.export(data, path)
        else:
            path = os.path.join(reports_dir, f"report_{report_id}.json")
            return JSONExporter.export(data, path)

    def download_folder_definition_xml(
        self,
        folder: str,
        ctm_server: str,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Descarga la definición XML nativa de un folder con todos sus jobs.

        Args:
            folder: Nombre exacto del folder.
            ctm_server: Servidor Control-M que contiene el folder.
            output_path: Ruta opcional. Si se omite, guarda el XML en
                ``<output_dir>/folder_definitions/<folder>.xml``.

        Returns:
            Ruta absoluta del archivo XML creado.
        """
        content = self.client.get_folder_definition_xml(folder, ctm_server)

        if output_path is None:
            definitions_dir = os.path.join(self.output_dir, "folder_definitions")
            safe_folder = "".join(
                character if character.isalnum() or character in "._-" else "_"
                for character in folder
            ).rstrip(". ")
            output_path = os.path.join(definitions_dir, f"{safe_folder}.xml")

        absolute_path = os.path.abspath(output_path)
        temporary_path = f"{absolute_path}.part"
        try:
            os.makedirs(os.path.dirname(absolute_path) or ".", exist_ok=True)
            with open(temporary_path, "wb") as output_file:
                output_file.write(content)
            os.replace(temporary_path, absolute_path)
            return absolute_path
        except OSError as exc:
            try:
                os.remove(temporary_path)
            except OSError:
                pass
            raise ExportError(
                f"Error guardando la definición XML del folder: {exc}"
            ) from exc

    def list_available_reports(self) -> list[dict]:
        """Lista reportes disponibles en la sección Reports."""
        return self.client.get_reports()

    def list_folders(self, ctm_server: Optional[str] = None) -> list[dict]:
        """Lista folders disponibles."""
        return self.client.get_folders(ctm_server=ctm_server)

    def close(self):
        """Cierra la sesión."""
        self.client.logout()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
