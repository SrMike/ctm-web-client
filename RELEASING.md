# Publicación de una versión

La publicación utiliza GitHub Releases y PyPI Trusted Publishing. No requiere
guardar un token de PyPI en GitHub ni en el repositorio.

## Requisitos iniciales

### Environment de GitHub

En el repositorio `SrMike/ctm-web-client`:

1. Abre **Settings → Environments**.
2. Crea un environment llamado `pypi`.
3. Opcionalmente exige aprobación manual para despliegues.

### Trusted Publisher de PyPI

En el proyecto `ctm-web-client` de PyPI:

1. Abre **Manage → Publishing**.
2. Agrega un publisher de GitHub Actions con:
   - Owner: `SrMike`
   - Repository: `ctm-web-client`
   - Workflow: `publish-pypi.yml`
   - Environment: `pypi`

Estos valores deben coincidir exactamente con
`.github/workflows/publish-pypi.yml`.

## Preparar el código

1. Actualiza la versión en `pyproject.toml` y `ctm_web_client/__init__.py`.
2. Actualiza `README.md` y `CHANGELOG.md`.
3. Ejecuta las pruebas unitarias.
4. Verifica que no haya secretos, XML reales, logs, outputs ni capturas.
5. Confirma los cambios y sincroniza la rama `main` desde el panel de Control de
   código fuente de VS Code.

La versión 2.1.0 debe incluir:

- `.github/workflows/publish-pypi.yml`
- `.gitignore`
- `CHANGELOG.md`
- `MANIFEST.in`
- `README.md`
- `RELEASING.md`
- `example_usage.py`
- `pyproject.toml`
- `ctm_web_client/__init__.py`
- `ctm_web_client/client_v2.py`
- `ctm_web_client/downloader.py`
- `tests/test_folder_xml.py`

No debe incluir:

- `.venv/`
- `dist/`
- `discovery/`
- perfiles o capturas de navegador
- `folder_download_*/`
- XML reales
- logs u outputs
- archivos con passwords, tokens o cookies

## Crear el Release

Después de sincronizar `main`:

1. Abre **Releases → Draft a new release**.
2. Crea el tag `v2.1.0` desde la rama `main` actualizada.
3. Usa el título `ctm-web-client 2.1.0`.
4. Copia el resumen de la sección 2.1.0 de `CHANGELOG.md`.
5. Publica el Release.

El evento activa el workflow de publicación. El workflow:

1. ejecuta las pruebas de `tests/`;
2. construye wheel y source distribution;
3. valida metadata y README con Twine;
4. publica en PyPI mediante una credencial OIDC temporal.

## Verificación posterior

1. Revisa el workflow en la pestaña **Actions**.
2. Confirma que la versión aparezca en
   `https://pypi.org/project/ctm-web-client/2.1.0/`.
3. Verifica que el wheel y el source distribution estén disponibles.
4. Instala 2.1.0 en un entorno limpio y comprueba
   `ctm_web_client.__version__`.

PyPI no permite reemplazar archivos de una versión publicada. Si la publicación
es incorrecta, corrige el código e incrementa la versión antes de publicar otra
vez.
