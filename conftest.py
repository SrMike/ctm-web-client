"""Asegura que las pruebas usen el código fuente local de ctm_web_client
en lugar de la copia instalada en .venv/Lib/site-packages (que puede estar
desactualizada, p. ej. sin ControlMDownloader o sin los métodos RF-Server).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
