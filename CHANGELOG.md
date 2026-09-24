# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.

## 2.2.0

### Corregido

- `delete_report()` (`DELETE /RF-Server/report/deleteReport`) fallaba
  siempre con HTTP 500 y cuerpo vacío, sin importar la forma de la
  petición (nombre de query param, verbo HTTP, presencia de body). Una
  captura real del navegador confirmó la causa: el servidor requiere
  `Accept: txt/html`, sin header `Content-Type`, y un header `server-name`
  con valor vacío — distinto de los headers por defecto de la sesión
  (`Accept`/`Content-Type: application/json` fijados en `login()`).
  `_rf_server_delete()` ahora aplica estos headers exactos. Validado en
  vivo end-to-end: borrado exitoso confirmado contra el catálogo real.
- `ControlMDownloader.download_report()` fallaba con
  `OSError: [Errno 22] Invalid argument` en Windows cuando el `report_id`
  contenía caracteres no válidos para nombres de archivo (p. ej. `*`, como
  en reportes cuyo nombre real termina en `_*`). El nombre de archivo de
  salida ahora se sanea (solo alfanuméricos y `._-`, el resto se reemplaza
  por `_`) antes de construir la ruta.

### Añadido

- `ControlMWebClient.create_report_from_file()`: crea (guarda) un reporte
  nuevo en el catálogo a partir de un archivo `.em.json`, como contraparte
  de `run_report_from_file()` (que solo ejecuta, no guarda). Reutiliza
  `list_saved_reports()`/`get_report_metadata()` para tomar el esqueleto
  de `columns` de un reporte existente con el mismo
  `reportDesignName`/`templateId`. Extraído y generalizado del flujo ya
  validado end-to-end en `test_report_lifecycle.py`. Validado en vivo
  (`test_create_report_from_file_20260923_175331.txt`): reporte creado,
  confirmado en el catálogo (15→16) y borrado limpio sin dejar huérfanos.
- Script `export_all_reports_em_json.py`: exporta todos los reportes
  guardados de la cuenta autenticada (`list_saved_reports()` +
  `get_report_metadata()`) como archivos `.em.json` individuales en
  `em_json_export/`, replicando el shape que produce el botón "Export" de
  la UI de Reports.
- Documentación (README.md, PROMPT_USO_BIBLIOTECA.md) del catálogo de
  reportes guardados vía RF-Server: `list_saved_reports()`,
  `get_report_metadata()`, `validate_report_name()`, `create_report()`,
  `save_report_as()`, `create_report_from_file()` y `delete_report()`,
  previamente no documentados.

### Pruebas

- Nueva suite `tests/test_report_catalog.py` (12 pruebas, sin red) que
  cubre los 7 métodos del catálogo RF-Server (`list_saved_reports()`,
  `get_report_metadata()`, `validate_report_name()`, `create_report()`,
  `save_report_as()`, `create_report_from_file()`, `delete_report()`) con
  datos completamente ficticios.
- Corregidos mocks desactualizados en `tests/test_reports.py` que ya no
  correspondían a los endpoints/atributos reales usados por
  `get_report_status()`/`download_report()`.

## 2.1.0

### Añadido

- `ControlMWebClient.get_folder_definition_xml()` descarga directamente la
  definición XML nativa de un folder y sus jobs, sin navegador ni scraping.
- `ControlMDownloader.download_folder_definition_xml()` guarda la definición
  mediante escritura binaria atómica.
- `ControlMDownloader` se exporta desde `ctm_web_client`.
- Validación estructural de XML: documento bien formado, raíz `DEFTABLE` y
  coincidencia exacta del folder solicitado.

### Documentación

- Se documenta que el cliente inicia sesión en Control-M Web y reutiliza esa
  sesión sobre endpoints internos REST, EmWebServices y Automation API.
- Se documenta que el endpoint de folders puede declarar `application/json`
  aunque devuelva XML.
- Se agregan ejemplos seguros que no incluyen credenciales, tokens, cookies,
  direcciones privadas ni información real de entornos.

### Validación

- La descarga directa se comparó con una exportación nativa de Workspace.
- Coincidieron 109 de 109 jobs y todos sus elementos funcionales, ignorando
  únicamente orden y metadata transitoria o de versión.

## 2.0.5

- Compatibilidad entre `ControlMDownloader` y `ControlMWebClient.get_jobs()`.
- Filtro local de `orderDate` en formatos `YYYY-MM-DD` y `YYYYMMDD`.

## 2.0.4

- Mejoras de documentación y preparación de publicación.
