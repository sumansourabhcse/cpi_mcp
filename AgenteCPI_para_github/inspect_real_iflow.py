"""
inspect_real_iflow.py — Descarga un iFlow real del tenant y muestra su estructura ZIP exacta.
"""
import sys, os, json, zipfile, io
sys.path.insert(0, os.path.dirname(__file__))

from tools import get_client

client = get_client()

# Usar un iFlow conocido del tenant
IFLOW_ID = "com.biogenesisXXXXX.s4hana.afip.wsfe.sendelectronicinvoicerequest"

print(f"Descargando: {IFLOW_ID}")
content = client.download_iflow(IFLOW_ID)
print(f"Descargado: {len(content):,} bytes")

zf = zipfile.ZipFile(io.BytesIO(content))

print("\n=== ESTRUCTURA DEL ZIP ===")
for name in sorted(zf.namelist()):
    info = zf.getinfo(name)
    print(f"  {info.file_size:>8,}  {name}")

# Mostrar XML del iflw (primeros 3000 chars)
for name in zf.namelist():
    if name.endswith(".iflw"):
        print(f"\n=== {name} (primeros 3000 chars) ===")
        print(zf.read(name).decode("utf-8", errors="replace")[:3000])
        break

# Mostrar archivos clave
for key_file in ["META-INF/MANIFEST.MF", "metainfo.prop"]:
    if key_file in zf.namelist():
        print(f"\n=== {key_file} ===")
        print(zf.read(key_file).decode("utf-8", errors="replace"))

# Mostrar .project si existe
for name in zf.namelist():
    if name.endswith(".project"):
        print(f"\n=== {name} ===")
        print(zf.read(name).decode("utf-8", errors="replace"))
        break
