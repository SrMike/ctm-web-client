"""
Cliente para Control-M/EM Web — verificado por ingeniería inversa.

Autenticación confirmada (Phase 1-5 discovery):
- Login: POST /ControlM/rest/EmWebServices/login (protobuf base64)
- REST endpoints: Header "Authorization: Bearer <EM_TOKEN>"
- EmWebServices: body {"data": "<protobuf con username+token en base64>"}
- Sesión: cookies JSESSIONID + EM_TOKEN

El cliente reutiliza la sesión web en endpoints REST, EmWebServices y rutas
internas de Automation API. No realiza un login independiente de Automation API.
"""

import base64
import logging
import warnings
from typing import Optional
from xml.etree import ElementTree

import requests

from ctm_web_client.exceptions import (
    AuthenticationError,
    ControlMWebError,
    ResourceNotFoundError,
    SessionExpiredError,
)

logger = logging.getLogger(__name__)

# Suprimir warnings SSL
warnings.filterwarnings("ignore", message="Unverified HTTPS request")
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    pass


# ─── Protobuf helpers ─────────────────────────────────────────────────────────

def _proto_string(field_num: int, value: str) -> bytes:
    """Codifica un string en protobuf wire format."""
    tag = (field_num << 3) | 2
    encoded = value.encode("utf-8")
    length = len(encoded)
    if length < 128:
        return bytes([tag, length]) + encoded
    result = bytes([tag])
    l = length
    while l > 0x7F:
        result += bytes([(l & 0x7F) | 0x80])
        l >>= 7
    result += bytes([l])
    result += encoded
    return result


def _proto_varint(field_num: int, value: int) -> bytes:
    """Codifica un varint en protobuf wire format."""
    tag = (field_num << 3) | 0
    return bytes([tag, value])


# ─── Cliente principal ────────────────────────────────────────────────────────

class ControlMWebClient:
    """
    Cliente HTTP para Control-M/EM Web (on-premise).

    Usa los endpoints internos de la interfaz web para extraer datos. Algunas
    operaciones reutilizan la sesión web en rutas internas de Automation API.

    Args:
        base_url: URL base (ej: "https://server:8443/ControlM")
        verify_ssl: Verificar certificados SSL (default False para self-signed).
        timeout: Timeout por request en segundos.

    Ejemplo:
        client = ControlMWebClient("https://controlm-server:8443/ControlM")
        client.login("usuario", "password")
        viewpoints = client.get_viewpoints()
        servers = client.get_servers_info()
        client.logout()
    """

    def __init__(
        self,
        base_url: str,
        verify_ssl: bool = False,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._session: Optional[requests.Session] = None
        self._authenticated = False
        self._em_token: Optional[str] = None
        self._username: Optional[str] = None
        self._auth_data: Optional[str] = None  # protobuf base64 para EmWebServices

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    # ─────────────────────────────────────────────────────────────────────
    # HTTP internals
    # ─────────────────────────────────────────────────────────────────────

    def _rest_get(self, path: str, **kwargs) -> requests.Response:
        """GET a un REST endpoint con Bearer auth."""
        if not self._session or not self._authenticated:
            raise ControlMWebError("No autenticado. Ejecuta login() primero.")

        url = f"{self.base_url}/rest/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self._em_token}"}

        resp = self._session.get(
            url, headers=headers, verify=self.verify_ssl, timeout=self.timeout, **kwargs
        )
        self._check_response(resp, url)
        return resp

    def _rest_post(self, path: str, json_body=None, **kwargs) -> requests.Response:
        """POST a un REST endpoint con Bearer auth."""
        if not self._session or not self._authenticated:
            raise ControlMWebError("No autenticado. Ejecuta login() primero.")

        url = f"{self.base_url}/rest/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self._em_token}"}

        resp = self._session.post(
            url, json=json_body, headers=headers,
            verify=self.verify_ssl, timeout=self.timeout, **kwargs
        )
        self._check_response(resp, url)
        return resp

    def _em_service(self, service_name: str, extra_proto: bytes = b"") -> dict:
        """
        Llama a un EmWebService con autenticación protobuf.

        Args:
            service_name: Nombre del servicio.
            extra_proto: Bytes protobuf adicionales después de username+token.

        Returns:
            Response JSON (contiene campo "data" con protobuf base64).
        """
        if not self._session or not self._authenticated:
            raise ControlMWebError("No autenticado. Ejecuta login() primero.")

        url = f"{self.base_url}/rest/EmWebServices/{service_name}"
        auth_bytes = _proto_string(1, self._username) + _proto_string(2, self._em_token)
        payload = base64.b64encode(auth_bytes + extra_proto).decode("ascii")

        resp = self._session.post(
            url, json={"data": payload},
            verify=self.verify_ssl, timeout=self.timeout
        )
        self._check_response(resp, url)
        return resp.json()

    def _em_service_raw(self, service_name: str, data: str = "") -> dict:
        """Llama EmWebService con data arbitrario (ya codificado)."""
        url = f"{self.base_url}/rest/EmWebServices/{service_name}"
        resp = self._session.post(
            url, json={"data": data},
            verify=self.verify_ssl, timeout=self.timeout
        )
        self._check_response(resp, url)
        return resp.json()

    def _check_response(self, resp: requests.Response, url: str):
        if resp.status_code == 401:
            self._authenticated = False
            raise SessionExpiredError("Sesión expirada. Ejecuta login() de nuevo.")
        if resp.status_code == 404:
            raise ResourceNotFoundError(f"No encontrado: {url}")
        if resp.status_code >= 500:
            raise ControlMWebError(f"Error servidor {resp.status_code}: {url}")

    def _decode_em_data(self, response: dict) -> bytes:
        """Decodifica el campo 'data' protobuf de un EmWebService response."""
        raw = response.get("data", "")
        if raw:
            return base64.b64decode(raw)
        return b""

    # ─────────────────────────────────────────────────────────────────────
    # Autenticación
    # ─────────────────────────────────────────────────────────────────────

    def login(self, username: str, password: str) -> None:
        """
        Autentica contra Control-M/EM Web.

        Usa el mismo mecanismo que el navegador:
        POST /rest/EmWebServices/login con protobuf(username, password, domain, flag)
        """
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._username = username

        # Construir protobuf de login (formato verificado en discovery Phase 1)
        login_proto = (
            _proto_string(1, username)
            + _proto_string(2, password)
            + _proto_string(3, username)  # domain
            + _proto_varint(4, 1)          # flag
        )
        login_data = base64.b64encode(login_proto).decode("ascii")

        url = f"{self.base_url}/rest/EmWebServices/login"
        try:
            resp = self._session.post(
                url, json={"data": login_data},
                verify=self.verify_ssl, timeout=self.timeout
            )
        except requests.exceptions.ConnectionError as e:
            raise ControlMWebError(f"No se pudo conectar a Control-M: {e}")

        if resp.status_code != 200:
            raise AuthenticationError(
                f"Login falló (HTTP {resp.status_code}): {resp.text[:300]}"
            )

        # Detectar error en el body protobuf (ej: MAX_CONCURRENT_USER_SESSIONS)
        try:
            resp_json = resp.json()
            if resp_json.get("data"):
                decoded_body = base64.b64decode(resp_json["data"])
                body_text = decoded_body.decode("utf-8", errors="replace")
                if "MAX_CONCURRENT" in body_text or "Internal server Error" in body_text:
                    raise AuthenticationError(
                        f"Sesiones concurrentes agotadas. Cierra sesiones en el navegador "
                        f"y espera unos minutos. Detalle: {body_text[:150]}"
                    )
        except AuthenticationError:
            raise
        except Exception:
            pass  # Si no se puede parsear, continuar

        # Extraer EM_TOKEN de cookies
        em_token = None
        for cookie in self._session.cookies:
            if cookie.name == "EM_TOKEN":
                em_token = cookie.value
                break

        if not em_token:
            # Fallback: GET /rest/em-token
            try:
                resp2 = self._session.get(
                    f"{self.base_url}/rest/em-token",
                    verify=self.verify_ssl, timeout=10
                )
                if resp2.status_code == 200:
                    data = resp2.json()
                    em_token = data.get("EM_TOKEN") or data.get("token", "")
            except Exception:
                pass

        if not em_token:
            # Último intento: extraer del protobuf response (token hex largo)
            try:
                resp_json = resp.json()
                if resp_json.get("data"):
                    decoded = base64.b64decode(resp_json["data"])
                    # Buscar strings hex largos que sean el token
                    pos = 0
                    while pos < len(decoded):
                        if pos + 1 < len(decoded) and (decoded[pos] & 0x07) == 2:
                            length = decoded[pos + 1]
                            if 20 < length < 128 and pos + 2 + length <= len(decoded):
                                try:
                                    s = decoded[pos+2:pos+2+length].decode('ascii')
                                    if all(c in '0123456789ABCDEFabcdef' for c in s):
                                        em_token = s
                                        break
                                except (UnicodeDecodeError, ValueError):
                                    pass
                        pos += 1
            except Exception:
                pass

        if not em_token:
            raise AuthenticationError(
                "Login exitoso pero no se obtuvo EM_TOKEN. "
                "Posibles causas: sesiones concurrentes agotadas o error del servidor."
            )

        self._em_token = em_token
        self._authenticated = True
        logger.info("Login exitoso en Control-M Web.")

    def logout(self) -> None:
        """
        Cierra la sesión. Intenta múltiples métodos para asegurar
        que la sesión se libere en el servidor.
        """
        if not self._session:
            return

        # Intento 1: EmWebServices/logout con protobuf auth
        if self._em_token and self._username:
            try:
                url = f"{self.base_url}/rest/EmWebServices/logout"
                auth_bytes = _proto_string(1, self._username) + _proto_string(2, self._em_token)
                payload = base64.b64encode(auth_bytes).decode("ascii")
                self._session.post(url, json={"data": payload}, verify=self.verify_ssl, timeout=10)
            except Exception:
                pass

        # Intento 2: Automation API session/logout
        try:
            api_base = self.base_url.rsplit('/ControlM', 1)[0]
            headers = {"Authorization": f"Bearer {self._em_token}"} if self._em_token else {}
            self._session.post(
                f"{api_base}/automation-api/session/logout",
                json={}, headers=headers, verify=self.verify_ssl, timeout=10
            )
        except Exception:
            pass

        # Intento 3: Invalidar cookie forzando cierre de sesión HTTP
        try:
            self._session.cookies.clear()
        except Exception:
            pass

        # Limpiar estado local
        try:
            self._session.close()
        except Exception:
            pass
        self._session = None
        self._authenticated = False
        self._em_token = None
        logger.info("Sesión cerrada.")

    @staticmethod
    def force_logout(
        base_url: str,
        username: str,
        password: str,
        verify_ssl: bool = False,
        timeout: int = 30,
    ) -> bool:
        """
        Fuerza el cierre de sesiones abiertas en el servidor.

        Hace login y logout inmediato para liberar slots de sesiones
        concurrentes que hayan quedado huerfanas.

        Args:
            base_url: URL base de Control-M (ej: "https://server:8443/ControlM").
            username: Usuario.
            password: Contraseña.
            verify_ssl: Verificar SSL.
            timeout: Timeout por request.

        Returns:
            True si se logro hacer login+logout exitosamente.
        """
        session = requests.Session()
        session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        base_url = base_url.rstrip("/")

        # Login
        login_proto = (
            _proto_string(1, username)
            + _proto_string(2, password)
            + _proto_string(3, username)
            + _proto_varint(4, 1)
        )
        login_data = base64.b64encode(login_proto).decode("ascii")

        try:
            resp = session.post(
                f"{base_url}/rest/EmWebServices/login",
                json={"data": login_data},
                verify=verify_ssl, timeout=timeout,
            )
        except Exception:
            session.close()
            return False

        if resp.status_code != 200:
            session.close()
            return False

        # Obtener token
        em_token = None
        for cookie in session.cookies:
            if cookie.name == "EM_TOKEN":
                em_token = cookie.value

        if not em_token:
            session.close()
            return False

        # Logout via EmWebServices
        try:
            auth_bytes = _proto_string(1, username) + _proto_string(2, em_token)
            payload = base64.b64encode(auth_bytes).decode("ascii")
            session.post(
                f"{base_url}/rest/EmWebServices/logout",
                json={"data": payload},
                verify=verify_ssl, timeout=timeout,
            )
        except Exception:
            pass

        # Logout via Automation API
        try:
            api_base = base_url.rsplit('/ControlM', 1)[0]
            session.post(
                f"{api_base}/automation-api/session/logout",
                json={},
                headers={"Authorization": f"Bearer {em_token}"},
                verify=verify_ssl, timeout=timeout,
            )
        except Exception:
            pass

        session.close()
        logger.info("Force logout completado.")
        return True

    # ─────────────────────────────────────────────────────────────────────
    # REST Endpoints (con Bearer token)
    # ─────────────────────────────────────────────────────────────────────

    def get_viewpoints(self) -> list:
        """Lista viewpoints disponibles."""
        resp = self._rest_get("viewpoints")
        return resp.json()

    def get_viewpoint_filters(self) -> list:
        """Obtiene filtros de viewpoints."""
        resp = self._rest_get("viewpointFilters")
        return resp.json()

    def get_environment(self) -> dict:
        """Info del entorno (mode, features, licenses)."""
        resp = self._rest_get("environment")
        return resp.json()

    def get_site_customizations(self) -> list:
        """Obtiene personalizaciones del sitio."""
        resp = self._rest_get("site-customizations?recordsLimit=10000")
        return resp.json()

    def get_user_data(self, category: str, sub_category: str = "") -> list:
        """Obtiene datos del usuario por categoría."""
        path = f"userData/getItemsInCategory?category={category}"
        if sub_category:
            path += f"&subCategory={sub_category}"
        resp = self._rest_get(path)
        return resp.json()

    # ─────────────────────────────────────────────────────────────────────
    # Automation API - Config/Info (confirmados Phase 11)
    # ─────────────────────────────────────────────────────────────────────

    def get_servers(self) -> list:
        """
        Lista servidores Control-M con host, estado y versión.

        Returns:
            Lista de dicts con name, host, state, version, ctmType.
        """
        resp = self._api_get("config/internal/servers")
        return resp.json()

    def get_effective_rights(self) -> dict:
        """Permisos efectivos del usuario autenticado."""
        resp = self._api_get("config/authorization/user/effectiveRights")
        return resp.json()

    def get_user_preferences(self) -> dict:
        """Preferencias del usuario."""
        resp = self._api_get(f"config/authorization/user/preferences?userName={self._username}")
        return resp.json()

    def get_auth_info(self) -> dict:
        """Info de autenticación (grupos, tipo de usuario)."""
        resp = self._api_get("config/internal/getAuthInfoFromMemory")
        return resp.json()

    def get_resources(self) -> list:
        """Lista recursos cuantitativos (semáforos)."""
        resp = self._api_get("run/resources")
        return resp.json()

    def get_workload_policies(self) -> dict:
        """Políticas de carga de trabajo."""
        resp = self._api_get("run/workloadpolicies")
        return resp.json()

    # ─────────────────────────────────────────────────────────────────────
    # EmWebServices (con protobuf auth)
    # ─────────────────────────────────────────────────────────────────────

    def get_servers_info(self) -> bytes:
        """
        Obtiene informacion de servidores Control-M.
        Retorna datos protobuf decodificados.
        """
        result = self._em_service("getCTMInformation")
        return self._decode_em_data(result)

    def get_topology(self) -> bytes:
        """Obtiene topología de la infraestructura."""
        result = self._em_service("GetTopology")
        return self._decode_em_data(result)

    def get_system_info(self) -> bytes:
        """Información del sistema."""
        result = self._em_service("getSystemInformation")
        return self._decode_em_data(result)

    def get_communication_status(self) -> bytes:
        """Estado de comunicación con servidores."""
        result = self._em_service("GetCommunicationStatus")
        return self._decode_em_data(result)

    def get_server_list(self) -> bytes:
        """Lista servidores con parámetros."""
        result = self._em_service("ListCTMDefsWithCTMParams")
        return self._decode_em_data(result)

    def get_fields_descriptors(self) -> bytes:
        """Descriptores de campos (para filtros)."""
        result = self._em_service("getFieldsDescSeq")
        return self._decode_em_data(result)

    def get_plugin_versions(self) -> bytes:
        """Versiones de plugins instalados."""
        result = self._em_service("getApplFieldsVersions")
        return self._decode_em_data(result)

    def get_license_info(self) -> bytes:
        """Información de licencia."""
        result = self._em_service("getLicenseInformation")
        return self._decode_em_data(result)

    def get_job_output(self, extra_params: bytes = b"") -> bytes:
        """
        Obtiene output de un job (requiere parámetros adicionales en protobuf).
        NOTA: Este endpoint existe (500 sin params) - requiere investigación
        adicional para los parámetros exactos del job.
        """
        result = self._em_service("getJobOutput", extra_params)
        return self._decode_em_data(result)

    # ─────────────────────────────────────────────────────────────────────
    # Alertas (REST con Bearer)
    # ─────────────────────────────────────────────────────────────────────

    def subscribe_alerts(self) -> dict:
        """Suscribirse a alertas (inicia stream de alertas)."""
        resp = self._rest_post("alerts/subscribe", json_body={})
        return resp.json() if resp.text else {}

    def unsubscribe_alerts(self) -> None:
        """Desuscribirse de alertas."""
        self._rest_post("alerts/unsubscribe", json_body={})

    def subscribe_alert_statistics(self) -> dict:
        """Suscribirse a estadísticas de alertas."""
        resp = self._rest_post("alerts/subscribeStatistics", json_body={})
        return resp.json() if resp.text else {}

    # ─────────────────────────────────────────────────────────────────────
    # Automation API interna (vía sesión web, sin login separado)
    # ─────────────────────────────────────────────────────────────────────

    def _api_get(self, path: str, **kwargs) -> requests.Response:
        """GET a la Automation API interna (Bearer + cookies de sesión)."""
        if not self._session or not self._authenticated:
            raise ControlMWebError("No autenticado. Ejecuta login() primero.")

        url = f"{self.base_url.rsplit('/ControlM', 1)[0]}/automation-api/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self._em_token}"}
        resp = self._session.get(
            url, headers=headers, verify=self.verify_ssl, timeout=self.timeout, **kwargs
        )
        self._check_response(resp, url)
        return resp

    def _api_post(self, path: str, json_body=None, **kwargs) -> requests.Response:
        """POST a la Automation API interna (Bearer + cookies de sesión)."""
        if not self._session or not self._authenticated:
            raise ControlMWebError("No autenticado. Ejecuta login() primero.")

        url = f"{self.base_url.rsplit('/ControlM', 1)[0]}/automation-api/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self._em_token}"}
        resp = self._session.post(
            url, json=json_body, headers=headers,
            verify=self.verify_ssl, timeout=self.timeout, **kwargs
        )
        self._check_response(resp, url)
        return resp

    # ─────────────────────────────────────────────────────────────────────
    # Reportes (Automation API /reporting/)
    # ─────────────────────────────────────────────────────────────────────

    def get_reports(self) -> list:
        """Lista reportes disponibles (intenta obtener la lista del servidor)."""
        # El endpoint reporting/report es POST — intentar obtener lista
        try:
            resp = self._api_get("reporting/report")
            return resp.json()
        except ControlMWebError:
            # En on-prem, puede no haber listado — retornar vacío
            return []

    def run_report(self, report_name: str, report_config: Optional[dict] = None) -> dict:
        """
        Ejecuta un reporte por nombre.

        Args:
            report_name: Nombre del reporte en Control-M.
            report_config: Configuración adicional (filtros, formato).
                Si None, ejecuta con defaults.

        Returns:
            Dict con resultado del reporte o datos de ejecución.
        """
        payload = {"name": report_name}
        if report_config:
            payload.update(report_config)
        resp = self._api_post("reporting/report", json_body=payload)
        return resp.json()

    def run_report_from_file(self, em_json_path: str, output_format: str = "CSV") -> dict:
        """
        Ejecuta un reporte desde un archivo .em.json.

        Args:
            em_json_path: Ruta al archivo .em.json.
            output_format: "CSV", "PDF", "EXCEL".

        Returns:
            Dict con resultado del reporte.
        """
        import json as _json
        with open(em_json_path, "r", encoding="utf-8") as f:
            config = _json.load(f)
        report_name = config.get("reportName", "")
        config["format"] = output_format
        return self.run_report(report_name, config)

    def get_report_filters(self, report_name: str) -> dict:
        """Obtiene filtros disponibles para un reporte."""
        resp = self._api_get(f"reporting/reportFilters/{report_name}")
        return resp.json()

    def get_report_status(self, report_id: str) -> dict:
        """Obtiene estado de generación de un reporte."""
        resp = self._api_get(f"reporting/status/{report_id}")
        return resp.json()

    def download_report(self, params: Optional[dict] = None) -> bytes:
        """
        Descarga un reporte generado previamente.

        Args:
            params: Dict con 'reportId' y opcionalmente otros parámetros.

        Returns:
            Bytes del archivo (CSV, PDF, Excel).
        """
        if not self._session or not self._authenticated:
            raise ControlMWebError("No autenticado. Ejecuta login() primero.")

        base = self.base_url.rsplit('/ControlM', 1)[0]
        url = f"{base}/automation-api/reporting/download"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"

        headers = {
            "Authorization": f"Bearer {self._em_token}",
            "Accept": "application/octet-stream",
        }
        resp = self._session.get(url, headers=headers, verify=self.verify_ssl, timeout=self.timeout)
        self._check_response(resp, url)
        return resp.content

    def wait_and_download_report(
        self,
        report_name: str,
        report_config: Optional[dict] = None,
        output_format: str = "CSV",
        poll_interval: int = 5,
        max_wait: int = 120,
    ) -> bytes:
        """
        Ejecuta un reporte, espera a que termine y descarga el resultado.

        Args:
            report_name: Nombre del reporte.
            report_config: Config adicional (filtros, etc).
            output_format: "CSV", "PDF", "EXCEL".
            poll_interval: Segundos entre cada verificación de estado.
            max_wait: Segundos máximos de espera.

        Returns:
            Bytes del archivo generado.

        Raises:
            ControlMWebError: Si el reporte falla o timeout.
        """
        import time

        # Ejecutar reporte
        config = report_config or {}
        config["format"] = output_format
        result = self.run_report(report_name, config)

        report_id = result.get("reportId", "")
        if not report_id:
            raise ControlMWebError(f"No se obtuvo reportId: {result}")

        # Polling hasta COMPLETED
        elapsed = 0
        while elapsed < max_wait:
            try:
                status_data = self.get_report_status(report_id)
                status = status_data.get("status", "UNKNOWN")
                if status in ("COMPLETED", "SUCCEEDED"):
                    # Descargar
                    return self.download_report({"reportId": report_id})
                elif status in ("FAILED", "ERROR"):
                    raise ControlMWebError(
                        f"Reporte falló: {status_data.get('message', status)}"
                    )
            except ResourceNotFoundError:
                pass  # Aún no disponible

            time.sleep(poll_interval)
            elapsed += poll_interval

        raise ControlMWebError(
            f"Timeout esperando reporte {report_id} (max {max_wait}s)"
        )

    # ─────────────────────────────────────────────────────────────────────
    # Jobs activos (Automation API /run/)
    # ─────────────────────────────────────────────────────────────────────

    def get_jobs_status(self, params: Optional[dict] = None) -> dict:
        """
        Obtiene estado de todos los jobs activos.

        Args:
            params: Filtros (limit, jobname, folder, ctm, status, etc).
        """
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            resp = self._api_get(f"run/jobs/status?{query}")
        else:
            resp = self._api_get("run/jobs/status")
        return resp.json()

    def get_job_status(self, job_id: str) -> dict:
        """Estado de un job específico."""
        resp = self._api_get(f"run/job/{job_id}/status")
        return resp.json()

    def get_job_log(self, job_id: str) -> str:
        """Log de ejecución de un job."""
        resp = self._api_get(f"run/job/{job_id}/log")
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type and resp.text.strip():
            try:
                data = resp.json()
                return data.get("log", data.get("output", resp.text))
            except (ValueError, KeyError):
                pass
        return resp.text

    def get_job_output(self, job_id: str, run_number: Optional[int] = None) -> str:
        """
        Output/sysout de un job.

        Args:
            job_id: ID del job (formato "SERVIDOR:RUNID").
            run_number: Numero de ejecucion especifico (0, 1, 2...).
                Si None, retorna el output de la ultima ejecucion.

        Returns:
            Texto del output.
        """
        path = f"run/job/{job_id}/output"
        if run_number is not None:
            path += f"?runNo={run_number}"
        resp = self._api_get(path)
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type and resp.text.strip():
            try:
                data = resp.json()
                return data.get("output", data.get("log", resp.text))
            except (ValueError, KeyError):
                pass
        return resp.text

    def get_job_statistics(self, job_id: str) -> dict:
        """Estadísticas de ejecución de un job."""
        resp = self._api_get(f"run/job/{job_id}/statistics")
        return resp.json()

    # ─────────────────────────────────────────────────────────────────────
    # Archive / Historial (Automation API /archive/)
    # ─────────────────────────────────────────────────────────────────────

    def search_archive(self, params: Optional[dict] = None) -> dict:
        """
        Busca en el archivo histórico de jobs.

        Args:
            params: Filtros de búsqueda (jobname, folder, ctm, from, to, etc).
        """
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            resp = self._api_get(f"archive/search?{query}")
        else:
            resp = self._api_get("archive/search")
        return resp.json()

    def get_archive_log(self, run_id: str) -> str:
        """Log de una ejecución histórica."""
        resp = self._api_get(f"archive/{run_id}/log")
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            return resp.json().get("log", resp.text)
        return resp.text

    def get_archive_output(self, run_id: str) -> str:
        """Output de una ejecución histórica."""
        resp = self._api_get(f"archive/{run_id}/output")
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            return resp.json().get("output", resp.text)
        return resp.text

    # ─────────────────────────────────────────────────────────────────────
    # Alertas (Automation API /run/alerts/)
    # ─────────────────────────────────────────────────────────────────────

    def get_alerts(self, severity: Optional[str] = None) -> list:
        """
        Obtiene alertas activas.

        NOTA: En on-prem, run/alerts requiere POST con alertIds.
        Usa subscribe_alerts() del REST para obtener el stream.
        """
        # Intentar via REST (alerts/subscribe ya confirmado en Phase 8)
        try:
            resp = self._rest_post("alerts/subscribe", json_body={})
            data = resp.json()
            # El subscribe retorna un serverContextId, no las alertas directamente
            # Las alertas llegan por push/polling
            return data if isinstance(data, list) else [data]
        except ControlMWebError:
            return []

    def update_alerts(self, alert_ids: list, status: str = "Reviewed") -> dict:
        """
        Actualiza estado de alertas (requiere IDs específicos).

        Args:
            alert_ids: Lista de IDs de alertas.
            status: Nuevo estado ("Reviewed", "Closed", etc).
        """
        resp = self._api_post("run/alerts", json_body={
            "alertIds": alert_ids,
            "status": status,
        })
        return resp.json()

    # ─────────────────────────────────────────────────────────────────────
    # EmWebServices avanzados (jobs, folders, búsqueda)
    # ─────────────────────────────────────────────────────────────────────

    def get_folders_by_selection(self, filter_proto: bytes = b"") -> bytes:
        """Busca folders por selección. Requiere protobuf con filtro."""
        result = self._em_service("GetFoldersBySelection", filter_proto)
        return self._decode_em_data(result)

    def get_folder_jobs(self, filter_proto: bytes = b"") -> bytes:
        """Obtiene jobs de un folder por selección."""
        result = self._em_service("GetFolderJobsBySelection", filter_proto)
        return self._decode_em_data(result)

    def get_jobs_in_folder(self, folder_id_proto: bytes = b"") -> bytes:
        """Obtiene jobs en un folder por ID."""
        result = self._em_service("GetJobsInFolderById", folder_id_proto)
        return self._decode_em_data(result)

    def search_jobs_by_string(self, search_proto: bytes = b"") -> bytes:
        """Busca jobs por texto libre."""
        result = self._em_service("searchJobOnNetsByStr", search_proto)
        return self._decode_em_data(result)

    def get_service_list(self) -> bytes:
        """Lista de servicios (SLA/BIM)."""
        result = self._em_service("getServiceList")
        return self._decode_em_data(result)

    def get_service_jobs(self, service_key_proto: bytes = b"") -> bytes:
        """Jobs de un servicio específico."""
        result = self._em_service("getServiceJobs", service_key_proto)
        return self._decode_em_data(result)

    def get_folder_data(self, folder_proto: bytes = b"") -> bytes:
        """Datos de un folder (workbench)."""
        result = self._em_service("GetFolderData", folder_proto)
        return self._decode_em_data(result)

    def archive_invoke(self, request_proto: bytes = b"") -> bytes:
        """Invoca búsqueda en archivo."""
        result = self._em_service("archiveInvoke", request_proto)
        return self._decode_em_data(result)

    def archive_get_output(self, params_proto: bytes = b"") -> bytes:
        """Obtiene output de job archivado."""
        result = self._em_service("archiveGetOutput", params_proto)
        return self._decode_em_data(result)

    def do_job_action(self, action_proto: bytes = b"") -> bytes:
        """Ejecuta una acción sobre un job (hold, free, rerun, etc)."""
        result = self._em_service("doJobAction", action_proto)
        return self._decode_em_data(result)

    def get_job_documentation(self, job_key_proto: bytes = b"") -> bytes:
        """Obtiene documentación de un job."""
        result = self._em_service("getJobDocumentation", job_key_proto)
        return self._decode_em_data(result)

    # ─────────────────────────────────────────────────────────────────────
    # Helpers de alto nivel
    # ─────────────────────────────────────────────────────────────────────

    def get_jobs(
        self,
        folder: Optional[str] = None,
        job_name: Optional[str] = None,
        status: Optional[str] = None,
        ctm_server: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 1000,
    ) -> list:
        """
        Obtiene jobs activos con filtros.

        Args:
            folder: Filtrar por folder.
            job_name: Filtrar por nombre de job (soporta wildcards *).
            status: "Ended OK", "Ended Not OK", "Executing", "Wait Condition", etc.
            ctm_server: Servidor Control-M específico.
            date: Fecha de orden en formato YYYY-MM-DD o YYYYMMDD.
            limit: Máximo de resultados.
        """
        params = {"limit": str(limit)}
        if folder:
            params["folder"] = folder
        if job_name:
            params["jobname"] = job_name
        if status:
            params["status"] = status
        if ctm_server:
            params["ctm"] = ctm_server
        data = self.get_jobs_status(params)
        jobs = data.get("statuses", data) if isinstance(data, dict) else data
        if date and isinstance(jobs, list):
            normalized_date = date.replace("-", "")
            jobs = [
                job for job in jobs
                if isinstance(job, dict)
                and str(job.get("orderDate", "")).replace("-", "") == normalized_date
            ]
        return jobs

    def get_history(
        self,
        folder: Optional[str] = None,
        job_name: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 1000,
    ) -> dict:
        """
        Obtiene historial de ejecuciones.

        Intenta archive/search primero; si no está disponible (503),
        usa el reporte de forecast-execution.

        Args:
            folder: Filtrar por folder.
            job_name: Filtrar por nombre.
            date_from: Fecha inicio (YYYYMMDD).
            date_to: Fecha fin (YYYYMMDD).
            limit: Máximo de resultados.
        """
        # Intento 1: Archive API
        try:
            return self.search_archive({
                "folder": folder or "*",
                "jobname": job_name or "*",
                "from": date_from or "",
                "to": date_to or "",
                "limit": str(limit),
            })
        except ControlMWebError:
            pass

        # Intento 2: Reporte de ejecuciones
        try:
            report_name = "EJEC_CON_ESTADO_MX_*"
            return self.run_report(report_name, {
                "format": "CSV",
                "userData": {
                    "userFilters": [
                        {"columnId": "VIRTUAL-TIME-MENU", "value": "FromDateToDate"},
                        {"columnId": "START_DATE_IDX", "value": f"{date_from} {date_to}"},
                    ] + ([{"columnId": "APPLICATION", "operator": "In", "value": f"*{folder}*"}] if folder else []),
                },
            })
        except ControlMWebError:
            return {"error": "Ni archive ni reporting disponibles"}

    def get_folders(self, ctm_server: Optional[str] = None) -> list:
        """Lista folders disponibles (via Automation API)."""
        params = {}
        if ctm_server:
            params["ctm"] = ctm_server
        data = self.get_jobs_status(params)
        # Extraer folders únicos
        if isinstance(data, dict) and "statuses" in data:
            folders = set()
            for job in data["statuses"]:
                f = job.get("folder", "")
                if f:
                    folders.add(f)
            return [{"name": f} for f in sorted(folders)]
        return []

    def get_folder_definition_xml(
        self,
        folder: str,
        ctm_server: str,
    ) -> bytes:
        """
        Descarga la definición XML nativa de un folder y todos sus jobs.

        Usa la sesión web autenticada para consultar el endpoint interno
        ``GET /automation-api/deploy/jobs``. El servidor puede declarar
        incorrectamente ``application/json`` aunque el cuerpo sea XML, por lo
        que la validación se realiza sobre el contenido.

        Args:
            folder: Nombre exacto del folder.
            ctm_server: Nombre del servidor Control-M que contiene el folder.

        Returns:
            Documento XML original, sin recodificar, como bytes.

        Raises:
            ValueError: Si folder o ctm_server están vacíos.
            ControlMWebError: Si la respuesta no es un DEFTABLE válido o no
                contiene el folder solicitado.
        """
        folder = folder.strip()
        ctm_server = ctm_server.strip()
        if not folder:
            raise ValueError("folder no puede estar vacío.")
        if not ctm_server:
            raise ValueError("ctm_server no puede estar vacío.")

        response = self._api_get(
            "deploy/jobs",
            params={
                "format": "xml",
                "folder": folder,
                "ctm": ctm_server,
                "useArrayFormat": "false",
            },
        )
        if response.status_code >= 400:
            raise ControlMWebError(
                f"No se pudo descargar el folder {folder!r} "
                f"(HTTP {response.status_code})."
            )

        content = response.content
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as exc:
            raise ControlMWebError(
                f"El servidor no devolvió XML válido para el folder {folder!r}."
            ) from exc

        if root.tag != "DEFTABLE":
            raise ControlMWebError(
                f"Raíz XML inesperada para el folder {folder!r}: {root.tag!r}."
            )

        matching_folders = [
            node
            for node in root.findall(".//FOLDER")
            if node.get("FOLDER_NAME") == folder
        ]
        if len(matching_folders) != 1:
            raise ControlMWebError(
                f"La respuesta contiene {len(matching_folders)} folders "
                f"con nombre exacto {folder!r}; se esperaba uno."
            )

        return content

    def get_report_data(self, report_name: str, params: Optional[dict] = None) -> dict:
        """
        Obtiene datos de un reporte.

        Args:
            report_name: Nombre del reporte en Control-M.
            params: Parámetros adicionales (filtros, formato).
        """
        return self.run_report(report_name, params)

    # ─────────────────────────────────────────────────────────────────────
    # Context manager
    # ─────────────────────────────────────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()
        return False
