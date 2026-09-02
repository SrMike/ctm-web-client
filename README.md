# ctm-web-client

Cliente Python para **Control-M/EM Web** (on-premise). Permite descargar
definiciones XML nativas de folders, reportes, logs, outputs y consultar jobs.

Inicia sesión con el mecanismo de Control-M Web y reutiliza esa sesión en los
endpoints internos REST, EmWebServices y Automation API que usa la interfaz.
No requiere un login ni un token independiente de Automation API.

## Novedades de la versión 2.1.0

- Descarga directa de folders completos en XML nativo mediante
    `get_folder_definition_xml()`.
- Persistencia atómica mediante `download_folder_definition_xml()`.
- Validación de raíz `DEFTABLE` y coincidencia exacta del folder solicitado.
- `ControlMDownloader` disponible desde la API pública del paquete.
- Se mantienen el filtrado local por `orderDate` y las correcciones de
    compatibilidad de la versión 2.0.5.

## Instalacion

```bash
pip install ctm-web-client
```

O desde el codigo fuente:

```bash
pip install -e .
```

## Uso rapido

```python
import os
from getpass import getpass

from ctm_web_client import ControlMWebClient

base_url = os.environ.get("CTM_BASE_URL", "https://controlm.example:8443/ControlM")
username = os.environ.get("CTM_USERNAME", "usuario")
password = os.environ.get("CTM_PASSWORD") or getpass("Password: ")

with ControlMWebClient(base_url, verify_ssl=True) as client:
    client.login(username, password)

    # Jobs activos con filtros
    jobs = client.get_jobs(status="Ended Not OK", limit=100)
    for j in jobs:
        print(f"{j['jobId']} | {j['name']} | {j['status']}")

    # Log de ejecucion de un job
    log = client.get_job_log("CTM_SERVER:runid")
    print(log)

    # Output del proceso
    output = client.get_job_output("CTM_SERVER:runid")
    print(output)
```

## Reportes desde .em.json

Ejecuta cualquier reporte exportado de Control-M Web (archivos `.em.json`):

```python
import json

with open("mi_reporte.em.json") as f:
    config = json.load(f)

csv_bytes = client.wait_and_download_report(config["reportName"], config)

with open("reporte.csv", "wb") as f:
    f.write(csv_bytes)
```

## Funcionalidades

### Jobs activos

```python
# Listar todos (con limite)
jobs = client.get_jobs(limit=1000)

# Filtrar por nombre, folder, estado, servidor
jobs = client.get_jobs(
    job_name="MJOB*",
    status="Ended Not OK",
    ctm_server="CTM_SERVER1",
)

# Estado de un job especifico
status = client.get_job_status("CTM_SERVER1:abc123")
```

### Logs y Output

```python
# Log de Control-M (eventos, tiempos, recursos)
log = client.get_job_log("CTM_SERVER1:abc123")

# Output del proceso (stdout/stderr del script)
output = client.get_job_output("CTM_SERVER1:abc123")
```

### Definición XML nativa de un folder

La descarga directa incluye el folder y todos sus jobs definidos:

```python
xml_bytes = client.get_folder_definition_xml(
    folder="PRODUCCION",
    ctm_server="CTM_SERVER1",
)

with open("PRODUCCION.xml", "wb") as output_file:
    output_file.write(xml_bytes)
```

El método consulta `GET /automation-api/deploy/jobs` con `format=xml`, usando
la sesión web existente. Retorna `bytes` para preservar exactamente la
codificación enviada por Control-M. No confía en `Content-Type`, porque algunas
versiones declaran `application/json` aunque el cuerpo sea XML.

Antes de devolver el contenido, comprueba:

- XML bien formado;
- raíz `DEFTABLE`;
- exactamente un `FOLDER` con el nombre solicitado.

Para guardarlo desde la API de alto nivel:

```python
from ctm_web_client import ControlMDownloader

with ControlMDownloader(
    base_url,
    username,
    password,
    output_dir="./controlm_output",
    verify_ssl=True,
) as downloader:
    path = downloader.download_folder_definition_xml(
        folder="PRODUCCION",
        ctm_server="CTM_SERVER1",
    )
    print(path)
```

Por defecto se guarda en
`controlm_output/folder_definitions/PRODUCCION.xml`. También acepta
`output_path` para elegir otra ubicación. La escritura usa un archivo temporal
`.part` y reemplazo atómico para no dejar un XML incompleto.

### Reportes

```python
# Ejecutar reporte por nombre
result = client.run_report("ACTIVO-MX-*", config)

# Todo en uno: ejecutar, esperar y descargar
csv_bytes = client.wait_and_download_report("Jobs Definitions_1", config)
```

### Infraestructura

```python
# Servidores Control-M
servers = client.get_servers()

# Recursos cuantitativos
resources = client.get_resources()

# Permisos del usuario
rights = client.get_effective_rights()
```

### Exportadores

```python
from ctm_web_client.exporters import CSVExporter, JSONExporter, TextExporter

CSVExporter.export(jobs, "jobs.csv")
JSONExporter.export(data, "data.json")
TextExporter.export(log_text, "job.log")
```

### Decoder Protobuf

```python
from ctm_web_client import decode_nested, decode_strings

raw = client.get_servers_info()
parsed = decode_nested(raw)
```

## Tipos de reporte soportados (.em.json)

| Design | Descripcion |
|--------|-------------|
| `active-jobs.rptdesign` | Jobs en la red activa |
| `forecast-execution.rptdesign` | Historial de ejecuciones |
| `jobs-definitions.rptdesign` | Definiciones de jobs |

## Requisitos

- Python 3.10+
- Acceso de red al servidor Control-M/EM Web (puerto 8443)
- Credenciales de usuario web de Control-M
- Permiso para consultar los endpoints internos requeridos

## Notas

- El servidor tiene un limite bajo de sesiones concurrentes. Siempre usa `with` o llama `client.logout()`.
- En producción usa `verify_ssl=True`. Usa `verify_ssl=False` solamente en un
    entorno controlado con certificados autofirmados.
- Los `jobId` tienen formato `SERVIDOR:RUNID` (ej: `CTM_SERVER1:abc123`).
- Nunca guardes usuarios, passwords, tokens ni cookies en el código o logs.

## Licencia

GPL-3.0-or-later (Copyleft)

## Manejo de errores

```python
from ctm_web_client.exceptions import (
    AuthenticationError,
    SessionExpiredError,
    ResourceNotFoundError,
)

try:
    client.login(username, password)
except AuthenticationError as e:
    print(f"Login fallido: {e}")

try:
    log = client.get_job_log("ID_INVALIDO")
except ResourceNotFoundError:
    print("Job no encontrado")
except SessionExpiredError:
    print("La sesión expiró; vuelve a autenticar.")
```

## Notas importantes

- La biblioteca interactúa con endpoints internos no públicos de Control-M/EM.
    Las rutas, payloads y respuestas pueden cambiar entre versiones.
- La descarga XML directa fue validada con un folder de 109 jobs: los nombres,
    elementos y valores funcionales coincidieron con la exportación de Workspace.
- El XML directo puede diferir del exportado desde Workspace en indentación,
    orden, metadata de versión y ausencia del nodo transitorio `WORKSPACE`.
- La compatibilidad debe validarse contra cada instalación objetivo.

## Seguridad de publicación

Antes de publicar una versión, revisa que no se incluyan archivos locales,
capturas de navegador, outputs, logs, cookies, tokens, credenciales o URLs
internas. Los ejemplos de este documento utilizan valores ficticios.
