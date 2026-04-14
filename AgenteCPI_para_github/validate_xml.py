"""Valida el XML del iFlow antes de construir el ZIP."""
import sys, os, xml.etree.ElementTree as ET

# Leer el archivo y ejecutar solo hasta antes de build_zip()
src = open(os.path.join(os.path.dirname(__file__), "build_iflow_zip.py"),
           encoding="utf-8").read()
# Ejecutar solo las definiciones de variables
code = src.split("def build_zip():")[0]
ns = {}
exec(code, ns)

IFLOW_XML = ns["IFLOW_XML"]
print(f"Tamaño XML: {len(IFLOW_XML)} chars")

try:
    root = ET.fromstring(IFLOW_XML)
    print("XML VALIDO OK")
    print(f"  Root tag: {root.tag}")
except ET.ParseError as e:
    print(f"XML INVALIDO: {e}")
    # Mostrar contexto alrededor del error
    lines = IFLOW_XML.splitlines()
    lineno = e.position[0] if hasattr(e, 'position') else None
    if lineno:
        for i in range(max(0, lineno-3), min(len(lines), lineno+2)):
            marker = ">>>" if i == lineno-1 else "   "
            print(f"  {marker} L{i+1}: {lines[i]}")
    sys.exit(1)
