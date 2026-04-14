import zipfile, os

zdir = "generated_iflows"
for f in sorted(os.listdir(zdir)):
    if not f.endswith(".zip"):
        continue
    zpath = os.path.join(zdir, f)
    with zipfile.ZipFile(zpath, "r") as z:
        print(f"=== {f} ===")
        for name in z.namelist():
            print(f"  {name}")
        for name in z.namelist():
            if name.endswith(".groovy"):
                content = z.read(name).decode("utf-8")
                has_backticks = "```" in content
                first_line = content.split("\n")[0]
                print(f"  [{name}]")
                print(f"    backticks: {has_backticks}")
                print(f"    primera linea: {first_line[:80]}")
