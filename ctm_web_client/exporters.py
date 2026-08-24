"""
Exportadores de datos a diferentes formatos: JSON, CSV y texto plano.
"""

import csv
import json
import os
from typing import Union

from ctm_web_client.exceptions import ExportError


class JSONExporter:
    """Exporta datos a formato JSON."""

    @staticmethod
    def export(data: Union[list, dict], output_path: str, indent: int = 2) -> str:
        """
        Exporta datos a un archivo JSON.

        Args:
            data: Datos a exportar.
            output_path: Ruta del archivo de salida.
            indent: Indentación del JSON.

        Returns:
            Ruta absoluta del archivo creado.
        """
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False, default=str)
            return os.path.abspath(output_path)
        except (OSError, TypeError) as e:
            raise ExportError(f"Error exportando a JSON: {e}")

    @staticmethod
    def to_string(data: Union[list, dict], indent: int = 2) -> str:
        """Convierte datos a string JSON."""
        return json.dumps(data, indent=indent, ensure_ascii=False, default=str)


class CSVExporter:
    """Exporta datos a formato CSV."""

    @staticmethod
    def export(
        data: list[dict],
        output_path: str,
        delimiter: str = ",",
        columns: list[str] | None = None,
    ) -> str:
        """
        Exporta lista de diccionarios a CSV.

        Args:
            data: Lista de registros (dicts).
            output_path: Ruta del archivo de salida.
            delimiter: Separador de columnas.
            columns: Columnas específicas a incluir (None = todas).

        Returns:
            Ruta absoluta del archivo creado.
        """
        if not data:
            raise ExportError("No hay datos para exportar.")

        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

            # Determinar columnas
            if columns is None:
                columns = list(data[0].keys())

            with open(output_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=columns, delimiter=delimiter, extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(data)

            return os.path.abspath(output_path)
        except (OSError, ValueError) as e:
            raise ExportError(f"Error exportando a CSV: {e}")


class TextExporter:
    """Exporta logs y texto plano a archivos .log o .txt."""

    @staticmethod
    def export(content: str, output_path: str) -> str:
        """
        Guarda texto plano en un archivo.

        Args:
            content: Contenido de texto.
            output_path: Ruta del archivo de salida.

        Returns:
            Ruta absoluta del archivo creado.
        """
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            return os.path.abspath(output_path)
        except OSError as e:
            raise ExportError(f"Error exportando texto: {e}")

    @staticmethod
    def export_multiple(logs: dict[str, str], output_dir: str) -> list[str]:
        """
        Guarda múltiples logs en archivos separados.

        Args:
            logs: Dict {nombre_archivo: contenido}.
            output_dir: Directorio de salida.

        Returns:
            Lista de rutas de archivos creados.
        """
        os.makedirs(output_dir, exist_ok=True)
        paths = []
        for filename, content in logs.items():
            # Sanitizar nombre de archivo
            safe_name = "".join(
                c if c.isalnum() or c in "._-" else "_" for c in filename
            )
            path = os.path.join(output_dir, safe_name)
            paths.append(TextExporter.export(content, path))
        return paths
