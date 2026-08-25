# ctm-web-client

Cliente Python para **Control-M/EM Web** (on-premise). Permite descargar reportes, logs de ejecucion y monitorear jobs sin necesidad de privilegios de Automation API.

Funciona usando los mismos endpoints internos que utiliza la interfaz web de Control-M.

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
from ctm_web_client import ControlMWebClient

with ControlMWebClient("https://controlm-server:8443/ControlM", verify_ssl=False) as client:
    client.login("usuario", "password")

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
- Credenciales de usuario web de Control-M (no requiere privilegios de Automation API)

## Notas

- El servidor tiene un limite bajo de sesiones concurrentes. Siempre usa `with` o llama `client.logout()`.
- Los certificados SSL son self-signed en la mayoria de instalaciones on-premise. Usa `verify_ssl=False`.
- Los `jobId` tienen formato `SERVIDOR:RUNID` (ej: `CTM_SERVER1:abc123`).

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
    client.login("user", "wrong_pass")
except AuthenticationError as e:
    print(f"Login fallido: {e}")

try:
    log = client.get_job_log("ID_INVALIDO")
except ResourceNotFoundError:
    print("Job no encontrado")
except SessionExpiredError:
    client.login("user", "pass")  # Re-autenticar
```

## Notas importantes

- La biblioteca interactúa con los endpoints internos de la interfaz web de Control-M/EM. Los paths exactos pueden variar según la versión instalada.
- Si tu Control-M usa paths diferentes, puedes sobrescribir `ControlMWebClient._ENDPOINTS`.
- Para certificados SSL autofirmados, usa `verify_ssl=False`.
- Compatible con Control-M/EM v9.x y v20.x (Web interface).

## Personalizar endpoints

Si tu instalación de Control-M usa rutas diferentes:

```python
client = ControlMWebClient("https://server:8443/ControlM")
client._ENDPOINTS["jobs"] = "/web/api/monitoring/jobs"
client._ENDPOINTS["job_log"] = "/web/api/job/{job_id}/log"
client.login("user", "pass")
```
