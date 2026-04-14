"""
build_iflow_zip.py
==================
Toma un ZIP generado por el agente CPI, corrige su estructura
y lo empaqueta para importar en SAP CPI.

Uso:
    # Toma el ZIP mas reciente de generated_iflows/ automaticamente:
    py build_iflow_zip.py

    # O especifica un ZIP concreto:
    py build_iflow_zip.py generated_iflows/JSON_to_Interbanking_HTTP_20260324_150000.zip

Que corrige:
  - Namespace incorrecto en el .iflw XML
  - MANIFEST.MF incompleto (lo reemplaza con uno real del tenant)
  - .project con natures de Eclipse
  - metainfo.prop al formato correcto

Genera: <nombre_iflow>_fixed.zip  (listo para importar en CPI)
"""

import sys, os, io, zipfile, re, glob
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from tools import get_client

# iFlow del tenant que usamos para obtener el MANIFEST.MF real
TEMPLATE_ID = "com.biogenesisXXXXX.s4hana.afip.wsfe.sendelectronicinvoicerequest"

# Namespace incorrecto que genera el agente -> namespace correcto de SAP CPI
BAD_NS  = "http://sap.com/xi/ESBuildingBlock"
GOOD_NS = "http:///com.sap.ifl.model/Ifl.xsd"

# =============================================================================
# Helpers
# =============================================================================

def find_source_zip(arg=None):
    """Devuelve la ruta al ZIP fuente: el argumento o el mas reciente en generated_iflows/."""
    if arg:
        if not os.path.exists(arg):
            print(f"ERROR: No se encuentra el archivo: {arg}")
            sys.exit(1)
        return arg

    folder = os.path.join(os.path.dirname(__file__), "generated_iflows")
    zips   = sorted(glob.glob(os.path.join(folder, "*.zip")),
                    key=os.path.getmtime, reverse=True)
    if not zips:
        print("ERROR: No hay ZIPs en generated_iflows/")
        sys.exit(1)

    print(f"Usando ZIP mas reciente: {os.path.basename(zips[0])}")
    return zips[0]


def fix_namespace(xml_bytes: bytes) -> bytes:
    """Reemplaza el namespace incorrecto por el correcto en el XML del iflw."""
    text = xml_bytes.decode("utf-8")
    fixed = text.replace(BAD_NS, GOOD_NS)
    if BAD_NS in text:
        print("  [fix] Namespace del iflw corregido")
    else:
        print("  [ok]  Namespace del iflw ya es correcto")
    return fixed.encode("utf-8")


def patch_manifest(content: bytes, new_id: str, new_name: str) -> bytes:
    text = content.decode("utf-8")
    text = re.sub(
        r"^Bundle-SymbolicName:[ \t].*?(?=\r?\n(?![ \t]))",
        f"Bundle-SymbolicName: {new_id}; singleton:=true",
        text, flags=re.MULTILINE | re.DOTALL
    )
    text = re.sub(
        r"^Bundle-Name:[ \t].*?(?=\r?\n(?![ \t]))",
        f"Bundle-Name: {new_name}",
        text, flags=re.MULTILINE | re.DOTALL
    )
    text = re.sub(
        r"^Origin-Bundle-SymbolicName:[ \t].*?(?=\r?\n(?![ \t]))",
        f"Origin-Bundle-SymbolicName: {new_id}",
        text, flags=re.MULTILINE | re.DOTALL
    )
    text = re.sub(
        r"^Origin-Bundle-Name:[ \t].*?(?=\r?\n(?![ \t]))",
        f"Origin-Bundle-Name: {new_name}",
        text, flags=re.MULTILINE | re.DOTALL
    )
    text = re.sub(r"^Bundle-Version:[ \t].*", "Bundle-Version: 1.0.0",
                  text, flags=re.MULTILINE)
    return text.encode("utf-8")


def patch_dot_project(content: bytes, new_id: str) -> bytes:
    text = content.decode("utf-8")
    text = re.sub(r"<name>[^<]*</name>", f"<name>{new_id}</name>", text, count=1)
    return text.encode("utf-8")


def build_metainfo(description: str) -> bytes:
    ts   = datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S UTC %Y")
    desc = description.replace(",", "\\,").replace(":", "\\:")
    return f"#Store metainfo properties\n#{ts}\ndescription={desc}\n".encode("utf-8")


def read_iflow_metadata(src_zip: zipfile.ZipFile):
    """Lee el ID, nombre y descripcion del ZIP generado por el agente."""
    iflow_id   = ""
    iflow_name = ""
    desc       = ""

    # Intentar leer metainfo.prop
    if "metainfo.prop" in src_zip.namelist():
        raw  = src_zip.read("metainfo.prop").decode("utf-8", errors="replace")
        for line in raw.splitlines():
            if line.startswith("id="):
                iflow_id = line[3:].strip()
            elif line.startswith("display_name="):
                iflow_name = line[13:].strip()
            elif line.startswith("description="):
                desc = line[12:].strip()

    # Intentar leer del MANIFEST.MF si no encontramos en metainfo
    if not iflow_id and "META-INF/MANIFEST.MF" in src_zip.namelist():
        mf = src_zip.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
        for line in mf.splitlines():
            if line.startswith("Bundle-SymbolicName:"):
                raw_id = line.split(":", 1)[1].strip()
                iflow_id = raw_id.split(";")[0].strip()
            elif line.startswith("Bundle-Name:"):
                iflow_name = line.split(":", 1)[1].strip()

    # Fallback: usar el nombre del archivo .iflw
    if not iflow_id:
        for name in src_zip.namelist():
            if name.endswith(".iflw"):
                base = os.path.basename(name).replace(".iflw", "")
                iflow_name = iflow_name or base
                iflow_id   = re.sub(r"[^\w.]", "_", base).lower()
                break

    iflow_name = iflow_name or iflow_id
    return iflow_id, iflow_name, desc


# =============================================================================
# Main
# =============================================================================

def build_zip(source_arg=None):
    src_path = find_source_zip(source_arg)
    src_name = os.path.basename(src_path)
    print(f"\nFuente : {src_name}")

    src = zipfile.ZipFile(src_path)
    names = src.namelist()
    print(f"Archivos en fuente: {len(names)}")
    for n in sorted(names):
        print(f"  {src.getinfo(n).file_size:>8,}  {n}")

    # Leer metadatos del ZIP fuente
    iflow_id, iflow_name, description = read_iflow_metadata(src)
    print(f"\niFlow detectado:")
    print(f"  ID   : {iflow_id}")
    print(f"  Nombre: {iflow_name}")

    # Descargar MANIFEST.MF real del tenant
    print(f"\nDescargando MANIFEST.MF real del tenant...")
    client = get_client()
    raw_tmpl = client.download_iflow(TEMPLATE_ID)
    tmpl     = zipfile.ZipFile(io.BytesIO(raw_tmpl))
    mf       = patch_manifest(tmpl.read("META-INF/MANIFEST.MF"), iflow_id, iflow_name)
    proj     = patch_dot_project(tmpl.read(".project"), iflow_id)
    meta     = build_metainfo(description)

    # Construir ZIP de salida
    out_name = re.sub(r"_fixed\.zip$", "", src_name.replace(".zip", "")) + "_fixed.zip"
    out_path = os.path.join(os.path.dirname(src_path), out_name)

    iflw_entries = [n for n in names if n.endswith(".iflw")]
    iflw_base    = iflw_entries[0].rsplit("/", 1)[0] if iflw_entries else \
                   "src/main/resources/scenarioflows/integrationflow"
    new_iflw     = f"{iflw_base}/{iflow_name}.iflw"

    print(f"\nEmpaquetando: {out_name}")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as dst:
        dst.writestr("META-INF/MANIFEST.MF", mf)
        dst.writestr("metainfo.prop",         meta)
        dst.writestr(".project",              proj)

        for name in names:
            if name in ("META-INF/MANIFEST.MF", "metainfo.prop", ".project"):
                continue  # ya escritos con version corregida

            data = src.read(name)

            if name.endswith(".iflw"):
                data = fix_namespace(data)
                dst.writestr(new_iflw, data)
            else:
                dst.writestr(name, data)

    size = os.path.getsize(out_path)
    print(f"\nZIP listo: {out_name}  ({size:,} bytes)")
    print("\nContenido final:")
    with zipfile.ZipFile(out_path) as z:
        for n in z.namelist():
            print(f"  {z.getinfo(n).file_size:>8,}  {n}")

    # Validar XML
    import xml.etree.ElementTree as ET
    for n in zipfile.ZipFile(out_path).namelist():
        if n.endswith(".iflw"):
            xml_bytes = zipfile.ZipFile(out_path).read(n)
            try:
                ET.fromstring(xml_bytes)
                print("\nXML VALIDO OK")
            except ET.ParseError as e:
                print(f"\nXML INVALIDO: {e}")
            break

    print(f"\nListo -> importar en CPI: Design -> [Package] -> Add -> Upload")
    print(f"Archivo: {out_path}")
    return out_path


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    build_zip(arg)
