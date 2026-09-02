# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.

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
