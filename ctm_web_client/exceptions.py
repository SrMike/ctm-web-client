"""Excepciones personalizadas para ctm_web_client."""


class ControlMWebError(Exception):
    """Error base de la biblioteca."""
    pass


class AuthenticationError(ControlMWebError):
    """Error de autenticación contra Control-M Web."""
    pass


class SessionExpiredError(ControlMWebError):
    """La sesión expiró y se requiere re-autenticación."""
    pass


class ResourceNotFoundError(ControlMWebError):
    """El recurso solicitado (job, folder, reporte) no fue encontrado."""
    pass


class ExportError(ControlMWebError):
    """Error al exportar datos a archivo."""
    pass
