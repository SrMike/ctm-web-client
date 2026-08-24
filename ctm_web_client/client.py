"""Backward-compatible re-export. Usa client_v2 como implementacion canonica."""

from ctm_web_client.client_v2 import ControlMWebClient, _proto_string, _proto_varint

__all__ = ["ControlMWebClient", "_proto_string", "_proto_varint"]


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

        # Extraer EM_TOKEN
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
                    em_token = resp2.json().get("EM_TOKEN", "")
            except Exception:
                pass

        if not em_token:
            raise AuthenticationError("Login exitoso pero no se obtuvo EM_TOKEN.")

        self._em_token = em_token
        self._authenticated = True
        logger.info("Login exitoso en Control-M Web.")

    def logout(self) -> None:
        """Cierra la sesión."""
        if self._session and self._authenticated:
            try:
                self._em_service("logout")
            except Exception:
                pass
            finally:
                self._session.close()
                self._session = None
                self._authenticated = False
                self._em_token = None
                logger.info("Sesión cerrada.")

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
    # EmWebServices (con protobuf auth)
    # ─────────────────────────────────────────────────────────────────────

    def get_servers_info(self) -> bytes:
        """
        Obtiene información de servidores Control-M (CTM_CB, CTM_COLP, etc).
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
    # Reportes (pendiente discovery de endpoints específicos)
    # ─────────────────────────────────────────────────────────────────────

    # TODO: Endpoints de reportes .em.json por descubrir
    # Se agregarán después de capturar el tráfico de la sección Reports

    # ─────────────────────────────────────────────────────────────────────
    # Context manager
    # ─────────────────────────────────────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()
        return False
