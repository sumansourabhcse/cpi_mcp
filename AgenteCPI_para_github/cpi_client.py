import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)


class CPIClient:
    """Cliente de solo lectura para SAP Cloud Platform Integration (CPI)."""

    def __init__(self):
        self.client_id     = os.getenv("CPI_CLIENT_ID")
        self.client_secret = os.getenv("CPI_CLIENT_SECRET")
        self.base_url      = os.getenv("CPI_BASE_URL").rstrip("/")
        self.token_url     = os.getenv("CPI_TOKEN_URL")
        self._token        = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def _get_token(self) -> str:
        resp = requests.post(
            self.token_url,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=15,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _headers(self) -> dict:
        token = self._token or self._get_token()
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{self.base_url}/api/v1/{path.lstrip('/')}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=20)
        if resp.status_code == 401:
            self._token = None
            resp = requests.get(url, headers=self._headers(), params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Paquetes
    # ------------------------------------------------------------------
    def list_packages(self) -> list[dict]:
        """Devuelve todos los Integration Packages del tenant."""
        data = self._get("IntegrationPackages")
        return data.get("d", {}).get("results", [])

    def filter_packages(self, filter_text: str = "") -> list[dict]:
        """Devuelve paquetes filtrando por nombre o ID (case-insensitive)."""
        packages = self.list_packages()
        if not filter_text:
            return packages
        f = filter_text.lower()
        return [
            p for p in packages
            if f in p.get("Name", "").lower() or f in p.get("Id", "").lower()
        ]

    # ------------------------------------------------------------------
    # iFlows
    # ------------------------------------------------------------------
    def get_iflows_for_package(self, package_id: str) -> list[dict]:
        """Devuelve todos los iFlows de un paquete específico por su ID."""
        try:
            data = self._get(
                f"IntegrationPackages('{package_id}')/IntegrationDesigntimeArtifacts"
            )
            results = data.get("d", {}).get("results", [])
            # Enriquecer con info del paquete
            for item in results:
                item["_PackageId"] = package_id
            return results
        except requests.HTTPError:
            return []

    def list_iflows(self) -> list[dict]:
        """Devuelve todos los iFlows recorriendo todos los paquetes."""
        iflows = []
        for pkg in self.list_packages():
            pkg_id = pkg.get("Id")
            items  = self.get_iflows_for_package(pkg_id)
            for item in items:
                item["_PackageId"]   = pkg_id
                item["_PackageName"] = pkg.get("Name", "")
            iflows.extend(items)
        return iflows

    def download_iflow(self, iflow_id: str) -> bytes:
        """Descarga un iFlow como ZIP. Retorna los bytes del archivo."""
        url = (
            f"{self.base_url}/api/v1/"
            f"IntegrationDesigntimeArtifacts(Id='{iflow_id}',Version='active')/$value"
        )
        token = self._token or self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code == 401:
            self._token = None
            headers["Authorization"] = f"Bearer {self._get_token()}"
            resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.content

    def filter_iflows(self, package_filter: str = "") -> list[dict]:
        """Devuelve iFlows de los paquetes cuyo nombre/ID coincide con el filtro."""
        packages = self.filter_packages(package_filter) if package_filter else self.list_packages()
        iflows = []
        for pkg in packages:
            pkg_id = pkg.get("Id")
            items  = self.get_iflows_for_package(pkg_id)
            for item in items:
                item["_PackageId"]   = pkg_id
                item["_PackageName"] = pkg.get("Name", "")
            iflows.extend(items)
        return iflows
