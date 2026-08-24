"""
Decoder minimalista de protobuf wire format (sin .proto schema).

Parsea mensajes protobuf arbitrarios a una estructura genérica de campos.
Útil para interpretar respuestas de EmWebServices sin tener el .proto original.
"""

from __future__ import annotations

import base64
from typing import Union


def decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decodifica un varint. Retorna (valor, nueva_posición)."""
    result = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        result |= (byte & 0x7F) << shift
        pos += 1
        if (byte & 0x80) == 0:
            break
        shift += 7
    return result, pos


def decode_message(data: bytes) -> dict[int, list]:
    """
    Decodifica un mensaje protobuf en un dict de campos.

    Retorna:
        Dict donde key=field_number, value=lista de valores para ese campo.
        Los valores son:
        - int para wire type 0 (varint)
        - bytes para wire type 2 (length-delimited: puede ser string, bytes, o sub-message)
        - int para wire type 5 (32-bit fixed)
        - int para wire type 1 (64-bit fixed)
    """
    fields: dict[int, list] = {}
    pos = 0
    while pos < len(data):
        if pos >= len(data):
            break
        tag, pos = decode_varint(data, pos)
        field_num = tag >> 3
        wire_type = tag & 0x07

        if wire_type == 0:  # varint
            value, pos = decode_varint(data, pos)
        elif wire_type == 2:  # length-delimited
            length, pos = decode_varint(data, pos)
            value = data[pos:pos + length]
            pos += length
        elif wire_type == 5:  # 32-bit fixed
            value = int.from_bytes(data[pos:pos + 4], "little")
            pos += 4
        elif wire_type == 1:  # 64-bit fixed
            value = int.from_bytes(data[pos:pos + 8], "little")
            pos += 8
        else:
            break  # wire type desconocido

        fields.setdefault(field_num, []).append(value)

    return fields


def decode_strings(data: bytes) -> list[str]:
    """
    Extrae todos los strings UTF-8 legibles de un mensaje protobuf.
    Útil para un primer vistazo rápido al contenido.
    """
    fields = decode_message(data)
    strings = []
    for values in fields.values():
        for v in values:
            if isinstance(v, bytes):
                try:
                    s = v.decode("utf-8")
                    if s.isprintable() and len(s) > 0:
                        strings.append(s)
                except (UnicodeDecodeError, ValueError):
                    pass
    return strings


def decode_nested(data: bytes, max_depth: int = 3) -> dict:
    """
    Decodifica protobuf recursivamente intentando parsear sub-mensajes.

    Retorna estructura legible:
    {
        field_num: valor_o_lista_de_valores
    }
    Donde cada valor puede ser int, str, bytes(hex), o dict(sub-mensaje).
    """
    if max_depth <= 0:
        return {"_raw": data.hex()}

    fields = decode_message(data)
    result = {}

    for field_num, values in fields.items():
        parsed_values = []
        for v in values:
            if isinstance(v, int):
                parsed_values.append(v)
            elif isinstance(v, bytes):
                # Intentar decodificar como string UTF-8
                try:
                    s = v.decode("utf-8")
                    if s.isprintable():
                        parsed_values.append(s)
                        continue
                except (UnicodeDecodeError, ValueError):
                    pass
                # Intentar decodificar como sub-mensaje protobuf
                try:
                    sub = decode_nested(v, max_depth - 1)
                    if sub and len(sub) > 0 and "_raw" not in sub:
                        parsed_values.append(sub)
                        continue
                except Exception:
                    pass
                # Fallback: hex
                parsed_values.append(v.hex() if len(v) <= 64 else f"<{len(v)} bytes>")

        # Simplificar: si solo un valor, no usar lista
        if len(parsed_values) == 1:
            result[field_num] = parsed_values[0]
        else:
            result[field_num] = parsed_values

    return result


def decode_em_response(response_data: str, nested: bool = True) -> Union[dict, bytes]:
    """
    Decodifica el campo 'data' de una respuesta EmWebService.

    Args:
        response_data: String base64 del campo 'data' en la respuesta JSON.
        nested: Si True, intenta parsear recursivamente. Si False, retorna bytes.

    Returns:
        Dict con campos parseados o bytes raw.
    """
    raw = base64.b64decode(response_data)
    if nested:
        return decode_nested(raw)
    return raw
