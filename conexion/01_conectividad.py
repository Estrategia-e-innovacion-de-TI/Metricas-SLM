"""Etapa 1: comprobar que el modelo responde a través de LiteLLM."""
import json

from cliente import BASE_URL, MODELO, chat

print(f"Endpoint: {BASE_URL}")
print(f"Modelo:   {MODELO}\n")

respuesta, latencia, error = chat(
    [{"role": "user", "content": "Responde únicamente con la palabra LISTO"}],
    max_tokens=100,
)

if error:
    print(f"FALLÓ en {latencia:.2f}s\n{error}")
    if "Bearer Token has expired" in error:
        print("\n-> El token LiteLLM -> Bedrock está vencido. Lo debe renovar el equipo del gateway;"
              " una API key nueva de LiteLLM no lo soluciona por sí sola.")
    elif "HTTP 401" in error:
        print("\n-> La API key de LiteLLM es inválida o expiró. Pide una nueva.")
    raise SystemExit(1)

mensaje = respuesta["choices"][0]["message"]
print(f"OK en {latencia:.2f}s")
print(f"Contenido: {mensaje.get('content')!r}")
print(f"Uso de tokens: {json.dumps(respuesta.get('usage', {}))}")
