"""
Agente CLI para SAP CPI Integration Suite.

Usa Claude (Anthropic API) con tool_use para interpretar lenguaje natural
y consultar datos reales del tenant via las tools de tools.py.

Uso:
    python agent.py
    python agent.py "traeme los paquetes de Interbanking"   ← modo no-interactivo
"""

import sys
import json
import os
import anthropic
from dotenv import load_dotenv
from tools import (
    tool_list_packages, tool_list_iflows, tool_get_iflows_for_package,
    tool_backup_iflow, tool_analyze_iflow, tool_document_iflow,
    tool_get_iflow_profile, tool_detect_antipatterns,
    tool_regenerate_rag, tool_query_rag, tool_generate_iflow,
    tool_generate_iflow_zip,
)

load_dotenv(override=True)

MODEL       = "claude-sonnet-4-5"          # Agente principal + generación final de iFlows
MODEL_FAST  = "claude-haiku-4-5-20251001"  # Llamadas intermedias RAG (más barato, límites más altos)
SYSTEM  = (
    "Sos un asistente experto en SAP CPI (Cloud Platform Integration / Integration Suite). "
    "Respondés en español, de forma clara y concisa. "
    "Usás las tools disponibles para consultar datos reales del tenant. "
    "Cuando listás resultados, los mostrás en formato de tabla o lista ordenada. "
    "Si no encontrás resultados, lo decís claramente. "

    "REGLA — DISEÑO DE IFLOWS: "
    "Cuando el usuario pida crear, generar, armar, diseñar o construir un iFlow nuevo, "
    "respondés SIEMPRE con dos secciones bien diferenciadas: "
    "1) ENFOQUE GENERAL: descripción a alto nivel de la arquitectura, qué pattern de integración aplica, "
    "qué adapters recomiendas (sender/receiver), qué pasos de transformación son necesarios y por qué. "
    "2) PASO A PASO EN SAP CPI: instrucciones detalladas para construirlo manualmente en el designer, "
    "indicando para CADA paso: dónde hacer clic, qué adapter o step elegir, qué propiedades configurar "
    "y con qué valores (incluyendo expresiones Groovy, XPath o mappings relevantes si aplica). "
    "Usás query_rag para buscar iFlows similares del tenant y basar la guía en patrones reales ya usados. "
    "NO generás archivos ZIP automáticamente. "
    "Si el usuario quiere el ZIP después de ver la guía, puede pedirlo explícitamente. "

    "REGLA OBLIGATORIA — DOCUMENTACIÓN WORD: "
    "Cuando el usuario pida documentar, exportar a Word o generar un documento de un iFlow existente: "
    "primero llamás a analyze_iflow, luego redactás el análisis en Markdown, "
    "y finalmente llamás a document_iflow_to_word. Siempre mostrás: "
    "[⬇ Descargar DOCX](/download/DOCX_FILENAME) "

    "REGLA — ANÁLISIS: "
    "Cuando analizás un iFlow, examinás el BPMN, scripts Groovy/JS y mappings para explicar "
    "qué hace paso a paso, qué sistemas conecta, qué APIs/protocolos usa y cómo se autentica. "
)

# ------------------------------------------------------------------
# Definición de tools para la API de Anthropic
# ------------------------------------------------------------------
TOOLS = [
    {
        "name": "list_integration_packages",
        "description": (
            "Lista los Integration Packages del tenant SAP CPI. "
            "Acepta un filtro opcional para buscar por nombre o ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Texto para filtrar paquetes por nombre o ID (parcial, opcional).",
                }
            },
        },
    },
    {
        "name": "list_integration_flows",
        "description": (
            "Lista iFlows del tenant SAP CPI. "
            "Acepta un filtro por nombre de paquete para traer solo los iFlows "
            "de paquetes que coincidan con el texto dado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "package_filter": {
                    "type": "string",
                    "description": "Texto para filtrar por nombre de paquete (parcial, opcional).",
                }
            },
        },
    },
    {
        "name": "get_iflows_for_package",
        "description": "Obtiene todos los iFlows de un paquete dado su ID exacto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "package_id": {
                    "type": "string",
                    "description": "ID exacto del paquete.",
                }
            },
            "required": ["package_id"],
        },
    },
    {
        "name": "get_iflow_profile",
        "description": (
            "Parsea el XML del iFlow y devuelve un perfil técnico estructurado con: "
            "tipo de integración (síncrona/asíncrona), endpoints usados, "
            "adapters (SOAP/HTTP/OData/ProcessDirect/etc.), complejidad de mappings, "
            "uso de scripts Groovy/JS con métricas, y dependencias a otros iFlows. "
            "Usar cuando el usuario quiere un resumen técnico, un inventario de componentes, "
            "o comparar iFlows. Más rápido que analyze_iflow porque parsea directo sin IA."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "iflow_id": {
                    "type": "string",
                    "description": "ID exacto del iFlow a perfilar.",
                },
            },
            "required": ["iflow_id"],
        },
    },
    {
        "name": "analyze_iflow",
        "description": (
            "Descarga un iFlow de SAP CPI y analiza su contenido técnico completo: "
            "flujo BPMN, adapters usados, protocolos (HTTP/SOAP/OData/SFTP/etc.), "
            "autenticación (Basic/OAuth/Certificado), scripts Groovy o JavaScript, "
            "mappings y transformaciones. "
            "Usar cuando el usuario quiere entender qué hace un iFlow, cómo funciona, "
            "qué APIs usa, cómo se autentica, o pide una explicación técnica del mismo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "iflow_id": {
                    "type": "string",
                    "description": "ID exacto del iFlow a analizar.",
                },
            },
            "required": ["iflow_id"],
        },
    },
    {
        "name": "document_iflow_to_word",
        "description": (
            "Genera un documento Word (.docx) descargable con la documentación técnica "
            "completa de un iFlow de SAP CPI. Descarga el iFlow, analiza su contenido "
            "y produce el DOCX listo para descargar. "
            "Usar cuando el usuario pide documentar, exportar a Word, generar un documento "
            "o guardar la documentación de un iFlow. "
            "Retorna la URL de descarga del archivo generado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "iflow_id": {
                    "type": "string",
                    "description": "ID exacto del iFlow a documentar.",
                },
                "analysis_markdown": {
                    "type": "string",
                    "description": (
                        "Opcional. Documentación en Markdown ya generada previamente. "
                        "Si se omite, la tool genera el análisis automáticamente."
                    ),
                },
            },
            "required": ["iflow_id"],
        },
    },
    {
        "name": "backup_iflow_to_github",
        "description": (
            "Descarga un iFlow de SAP CPI y lo sube como backup a GitHub. "
            "Crea una carpeta con el ID del iFlow en el repo y nombra el archivo "
            "con el ID del iFlow más la fecha y hora actual (ej: MiIFlow_20240315_143022.zip). "
            "Usar cuando el usuario quiere hacer backup, guardar, descargar, "
            "exportar o subir un iFlow a GitHub."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "iflow_id": {
                    "type": "string",
                    "description": "ID exacto del iFlow a descargar y subir a GitHub.",
                },
            },
            "required": ["iflow_id"],
        },
    },
    {
        "name": "regenerate_rag",
        "description": (
            "Descarga TODOS los iFlows del tenant SAP CPI y reconstruye el índice "
            "vectorial RAG (ChromaDB) desde cero. Después de ejecutar esta tool, "
            "las tools de análisis incluirán automáticamente contexto del tenant "
            "(iFlows similares) en sus respuestas. "
            "ADVERTENCIA: puede tardar varios minutos según la cantidad de iFlows. "
            "La primera ejecución también descarga el modelo de embedding (~30 MB). "
            "Usar cuando el usuario pide 'regenerar el RAG', 'indexar los iFlows', "
            "'actualizar el contexto' o 'reconstruir el índice'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "query_rag",
        "description": (
            "Busca semánticamente en el índice RAG de iFlows del tenant. "
            "Retorna los N iFlows más similares a la consulta con metadata. "
            "Útil para encontrar iFlows de referencia, explorar el tenant, "
            "o buscar iFlows que usen ciertos adapters o patrones. "
            "Requiere haber ejecutado 'regenerate_rag' previamente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto de búsqueda semántica (ej: 'SOAP invoice integration', 'AFIP autenticación').",
                },
                "n_results": {
                    "type": "integer",
                    "description": "Cantidad de resultados a retornar (default: 5, máximo: 20).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "generate_iflow",
        "description": (
            "Busca en el RAG iFlows similares del tenant para basar la guía de diseño "
            "en patrones reales ya usados. Llamar cuando el usuario pide crear o diseñar "
            "un iFlow nuevo, para obtener contexto de referencia antes de responder."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Descripción detallada de qué debe hacer el iFlow: qué sistemas conecta, qué adapters usa, qué transformaciones aplica, etc.",
                },
                "iflow_name": {
                    "type": "string",
                    "description": "Nombre del iFlow (opcional). Si no se da, se genera desde la descripción.",
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "generate_iflow_zip",
        "description": (
            "Toma el XML BPMN2 de un iFlow y lo empaqueta en un ZIP con la estructura "
            "exacta que espera SAP CPI para importar: "
            "META-INF/MANIFEST.MF, metainfo.prop, parameters.prop, parameters.propdef, "
            "src/main/resources/scenarioflows/integrationflow/<id>.iflw, scripts Groovy y .project. "
            "Usar cuando el usuario tiene el XML de un iFlow y quiere el ZIP importable. "
            "Detecta automáticamente los parámetros externalizables {{NombreParam}} del XML. "
            "Retorna el path y la URL de descarga del ZIP generado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "iflow_xml": {
                    "type": "string",
                    "description": "Contenido XML BPMN2 completo del iFlow (.iflw).",
                },
                "iflow_name": {
                    "type": "string",
                    "description": "Nombre del iFlow (Bundle-Name y display_name).",
                },
                "iflow_id": {
                    "type": "string",
                    "description": "ID simbólico del iFlow (Bundle-SymbolicName). Si no se da, se genera desde el nombre.",
                },
                "scripts_json": {
                    "type": "string",
                    "description": 'JSON con los scripts Groovy a incluir. Formato: {"NombreScript.groovy": "contenido..."}. Default: "{}".',
                },
                "description": {
                    "type": "string",
                    "description": "Descripción del iFlow para metainfo.prop.",
                },
                "package_id": {
                    "type": "string",
                    "description": "ID del paquete al que pertenece el iFlow.",
                },
                "package_name": {
                    "type": "string",
                    "description": "Nombre técnico del paquete.",
                },
            },
            "required": ["iflow_xml", "iflow_name"],
        },
    },
    {
        "name": "detect_antipatterns",
        "description": (
            "Analiza un iFlow de SAP CPI en busca de anti-patrones de calidad, seguridad "
            "y mantenibilidad. Detecta 15 tipos de problemas: falta de Exception Subprocess, "
            "endpoints hardcodeados, credenciales en código, God Scripts, falta de try/catch, "
            "Thread.sleep, System.out.println, adapters deprecated, iFlows excesivamente "
            "complejos, mappings triviales, y más. "
            "Genera un score de calidad de 0 a 100 (EXCELENTE / BUENO / MEJORABLE / "
            "DEFICIENTE / CRITICO) con recomendaciones concretas para cada hallazgo. "
            "Usar cuando el usuario pide auditar, revisar la calidad, detectar problemas, "
            "analizar buenas prácticas, hacer code review o evaluar un iFlow."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "iflow_id": {
                    "type": "string",
                    "description": "ID exacto del iFlow a auditar.",
                },
            },
            "required": ["iflow_id"],
        },
    },
]

# ------------------------------------------------------------------
# Dispatcher de tools
# ------------------------------------------------------------------
TOOL_MAP = {
    "list_integration_packages": lambda args: tool_list_packages(args.get("filter", "")),
    "list_integration_flows":    lambda args: tool_list_iflows(args.get("package_filter", "")),
    "get_iflows_for_package":    lambda args: tool_get_iflows_for_package(args["package_id"]),
    "get_iflow_profile":         lambda args: tool_get_iflow_profile(args["iflow_id"]),
    "analyze_iflow":             lambda args: tool_analyze_iflow(args["iflow_id"]),
    "document_iflow_to_word":    lambda args: tool_document_iflow(args["iflow_id"], args.get("analysis_markdown", "")),
    "backup_iflow_to_github":    lambda args: tool_backup_iflow(args["iflow_id"]),
    "detect_antipatterns":       lambda args: tool_detect_antipatterns(args["iflow_id"]),
    "regenerate_rag":            lambda args: tool_regenerate_rag(),
    "query_rag":                 lambda args: tool_query_rag(args["query"], args.get("n_results", 5)),
    "generate_iflow":            lambda args: tool_generate_iflow(args["description"], args.get("iflow_name", "")),
    "generate_iflow_zip":        lambda args: tool_generate_iflow_zip(
                                     args["iflow_xml"],
                                     args["iflow_name"],
                                     args.get("iflow_id", ""),
                                     args.get("scripts_json", "{}"),
                                     args.get("description", ""),
                                     args.get("package_id", ""),
                                     args.get("package_name", ""),
                                 ),
}


def run_tool(name: str, args: dict) -> str:
    fn = TOOL_MAP.get(name)
    if not fn:
        return json.dumps({"error": f"Tool desconocida: {name}"})
    return fn(args)


# ------------------------------------------------------------------
# Loop del agente
# ------------------------------------------------------------------
def ask(client: anthropic.Anthropic, prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        # Respuesta final sin tool calls
        if response.stop_reason == "end_turn":
            return "".join(
                block.text for block in response.content if hasattr(block, "text")
            )

        # Hay tool calls → ejecutarlas
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            return "".join(
                block.text for block in response.content if hasattr(block, "text")
            )

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tc in tool_uses:
            print(f"  [tool] {tc.name}({json.dumps(tc.input, ensure_ascii=False)})")
            result = run_tool(tc.name, tc.input)
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tc.id,
                "content":     result,
            })

        messages.append({"role": "user", "content": tool_results})


# ------------------------------------------------------------------
# Entrada principal
# ------------------------------------------------------------------
def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: Falta ANTHROPIC_API_KEY en el .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Modo no-interactivo: python agent.py "tu pregunta"
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(f"Pregunta: {prompt}\n")
        print(ask(client, prompt))
        return

    # Modo interactivo
    print("╔══════════════════════════════════════════════╗")
    print("║   Agente CPI - SAP Integration Suite        ║")
    print("║   Escribí tu consulta o 'salir' para cerrar ║")
    print("╚══════════════════════════════════════════════╝\n")

    while True:
        try:
            user_input = input("Vos: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("salir", "exit", "quit"):
            print("Hasta luego.")
            break

        print()
        respuesta = ask(client, user_input)
        print(f"Agente: {respuesta}\n")


if __name__ == "__main__":
    main()
