"""
MCP Server para SAP CPI Integration Suite.

Puede usarse de dos formas:
  1. Directo desde Claude Desktop (stdio transport)
  2. Levantado como subprocess por agent.py

Herramientas expuestas:
  - list_integration_packages   → lista / filtra paquetes
  - list_integration_flows      → lista / filtra iFlows por paquete
  - get_iflows_for_package      → iFlows de un paquete específico
"""

from mcp.server.fastmcp import FastMCP
from tools import (
    tool_list_packages, tool_list_iflows, tool_get_iflows_for_package,
    tool_backup_iflow, tool_analyze_iflow, tool_document_iflow,
    tool_get_iflow_profile, tool_detect_antipatterns,
    tool_regenerate_rag, tool_query_rag, tool_generate_iflow,
    tool_generate_iflow_zip,
)

mcp = FastMCP("cpi-integration-suite")


@mcp.tool()
def list_integration_packages(filter: str = "") -> str:
    """
    Lista todos los Integration Packages del tenant SAP CPI.
    Parámetro opcional 'filter': filtra por nombre o ID (parcial, case-insensitive).
    Ejemplos: filter="interban", filter="Factura Electronica"
    """
    return tool_list_packages(filter)


@mcp.tool()
def list_integration_flows(package_filter: str = "") -> str:
    """
    Lista todos los iFlows del tenant SAP CPI.
    Parámetro opcional 'package_filter': filtra los iFlows mostrando solo los
    que pertenecen a paquetes cuyo nombre contiene el texto dado.
    Ejemplos: package_filter="Creatio", package_filter="Factura Electronica"
    Sin filtro devuelve todos los iFlows (puede ser lento con muchos paquetes).
    """
    return tool_list_iflows(package_filter)


@mcp.tool()
def get_iflows_for_package(package_id: str) -> str:
    """
    Obtiene todos los iFlows de un paquete específico dado su ID exacto.
    Ejemplo: package_id="com.biogenesisXXXXX.creatio.s4hana"
    """
    return tool_get_iflows_for_package(package_id)


@mcp.tool()
def get_iflow_profile(iflow_id: str) -> str:
    """
    Parsea el XML del iFlow y devuelve un perfil técnico estructurado:
    tipo de integración, endpoints, adapters, complejidad de mappings,
    scripts y dependencias. No usa IA — parsea el XML directamente.
    """
    return tool_get_iflow_profile(iflow_id)


@mcp.tool()
def analyze_iflow(iflow_id: str) -> str:
    """
    Descarga un iFlow de SAP CPI y extrae su contenido técnico completo:
    flujo BPMN (.iflw), scripts Groovy/JS, mappings XSLT y archivos de configuración.
    Permite analizar qué hace el iFlow, qué APIs usa y cómo se autentica.
    Ejemplo: iflow_id="com.biogenesisXXXXX.s4hana.afip.wsfe.sendelectronicinvoicerequest"
    """
    return tool_analyze_iflow(iflow_id)


@mcp.tool()
def document_iflow_to_word(iflow_id: str, analysis_markdown: str = "") -> str:
    """
    Genera un documento Word (.docx) con la documentación técnica de un iFlow.
    Recibe el ID del iFlow y la documentación en Markdown.
    Retorna la URL de descarga del archivo generado.
    """
    return tool_document_iflow(iflow_id, analysis_markdown)


@mcp.tool()
def backup_iflow_to_github(iflow_id: str) -> str:
    """
    Descarga un iFlow de SAP CPI y lo sube como backup a GitHub.
    Crea una carpeta {iflow_id}/ en el repo y nombra el archivo
    {iflow_id}_{YYYYMMDD_HHMMSS}.zip para trazabilidad de versiones.
    Ejemplo: iflow_id="com.biogenesisXXXXX.s4hana.afip.wsfe.sendelectronicinvoicerequest"
    """
    return tool_backup_iflow(iflow_id)


@mcp.tool()
def detect_antipatterns(iflow_id: str) -> str:
    """
    Analiza un iFlow de SAP CPI en busca de anti-patrones de calidad,
    seguridad y mantenibilidad. Detecta 15 categorías de problemas:
    falta de Exception Subprocess, endpoints hardcodeados, credenciales
    en código, God Scripts, falta de try/catch, Thread.sleep, adapters
    deprecated, y más. Genera un score de calidad 0-100 (EXCELENTE /
    BUENO / MEJORABLE / DEFICIENTE / CRITICO) con recomendaciones concretas.
    Ejemplo: iflow_id="com.biogenesisXXXXX.s4hana.afip.wsfe.sendelectronicinvoicerequest"
    """
    return tool_detect_antipatterns(iflow_id)


@mcp.tool()
def regenerate_rag() -> str:
    """
    Descarga TODOS los iFlows del tenant SAP CPI y reconstruye el índice
    vectorial RAG (ChromaDB) desde cero. Puede tardar varios minutos.
    La primera ejecución también descarga el modelo de embedding (~30 MB).
    """
    return tool_regenerate_rag()


@mcp.tool()
def query_rag(query: str, n_results: int = 5) -> str:
    """
    Búsqueda semántica en el índice RAG de iFlows del tenant.
    Retorna los iFlows más similares a la consulta.
    Requiere haber ejecutado regenerate_rag primero.
    """
    return tool_query_rag(query, n_results)


@mcp.tool()
def generate_iflow(description: str, iflow_name: str = "") -> str:
    """
    Genera un nuevo iFlow de SAP CPI desde cero usando el RAG del tenant como
    referencia. Produce un ZIP importable en SAP CPI. El archivo se guarda
    en generated_iflows/ con una URL de descarga disponible en el agente web.
    """
    return tool_generate_iflow(description, iflow_name)


@mcp.tool()
def generate_iflow_zip(
    iflow_xml:    str,
    iflow_name:   str,
    iflow_id:     str = "",
    scripts_json: str = "{}",
    description:  str = "",
    package_id:   str = "",
    package_name: str = "",
) -> str:
    """
    Toma el XML BPMN2 de un iFlow y lo empaqueta en un ZIP con la estructura
    exacta que espera SAP CPI para importar:
      META-INF/MANIFEST.MF, metainfo.prop, parameters.prop, parameters.propdef,
      src/main/resources/scenarioflows/integrationflow/<id>.iflw,
      src/main/resources/script/*.groovy (si hay scripts), .project
    Detecta automáticamente los parámetros externalizables {{NombreParam}}.
    """
    return tool_generate_iflow_zip(
        iflow_xml, iflow_name, iflow_id,
        scripts_json, description, package_id, package_name,
    )


if __name__ == "__main__":
    mcp.run()
