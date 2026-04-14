from cpi_client import CPIClient


def main():
    client = CPIClient()

    print("Conectando a SAP Integration Suite...")
    print(f"Tenant: {client.base_url}\n")

    print("Obteniendo paquetes...")
    packages = client.list_packages()
    print(f"Paquetes encontrados: {len(packages)}")
    for p in packages:
        print(f"  - [{p.get('Id')}] {p.get('Name')}")

    print("\nListando iFlows...")
    iflows = client.list_iflows()

    if not iflows:
        print("No se encontraron iFlows.")
        return

    print(f"\nTotal iFlows: {len(iflows)}\n")
    print(f"{'Paquete':<35} {'ID':<40} {'Version':<10} {'Estado'}")
    print("-" * 100)
    for f in iflows:
        print(
            f"{f.get('_PackageName', ''):<35} "
            f"{f.get('Id', ''):<40} "
            f"{f.get('Version', ''):<10} "
            f"{f.get('DeploymentStatus', '-')}"
        )


if __name__ == "__main__":
    main()
