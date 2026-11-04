"""Definiciones de herramientas simuladas (formato OpenAI tools).

El modelo solo PROPONE la llamada; en esta etapa no se ejecuta nada.
"""


def _tool(nombre, descripcion, parametro, desc_parametro):
    return {
        "type": "function",
        "function": {
            "name": nombre,
            "description": descripcion,
            "parameters": {
                "type": "object",
                "properties": {parametro: {"type": "string", "description": desc_parametro}},
                "required": [parametro],
                "additionalProperties": False,
            },
        },
    }


CONSULTAR_SOLICITUD = _tool(
    "consultar_solicitud",
    "Consulta el estado de una solicitud bancaria (crédito, apertura, reclamo). Los IDs tienen formato SOL-####.",
    "id_solicitud",
    "Identificador de la solicitud, por ejemplo SOL-1025",
)
CONSULTAR_TRANSACCION = _tool(
    "consultar_transaccion",
    "Consulta el detalle de una transacción o movimiento. Los IDs tienen formato TRX-####.",
    "id_transaccion",
    "Identificador de la transacción, por ejemplo TRX-5531",
)
CONSULTAR_PRODUCTO = _tool(
    "consultar_producto",
    "Consulta la información de un producto del cliente (cuenta, tarjeta, crédito). Los códigos tienen formato PRD-####.",
    "codigo_producto",
    "Código del producto, por ejemplo PRD-0042",
)

# Herramientas disponibles por nivel de complejidad
HERRAMIENTAS_POR_NIVEL = {
    1: [CONSULTAR_SOLICITUD],
    2: [CONSULTAR_SOLICITUD, CONSULTAR_TRANSACCION, CONSULTAR_PRODUCTO],
}

SYSTEM_PROMPT = (
    "Eres un asistente bancario de pruebas. Utiliza herramientas cuando corresponda. "
    "No inventes resultados ni identificadores. Si falta información necesaria, pídela al usuario."
)
