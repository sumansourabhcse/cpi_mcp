"""
Gestión del índice vectorial ChromaDB para el contexto de iFlows del tenant SAP CPI.

Usa ChromaDB con DefaultEmbeddingFunction (all-MiniLM-L6-v2 via ONNX Runtime).
El modelo se descarga automáticamente la primera vez (~30 MB).
La base de datos se persiste en rag_db/ dentro del directorio del proyecto.
"""

import os

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

# Directorio de persistencia
_BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
RAG_DIR         = os.path.join(_BASE_DIR, "rag_db")
COLLECTION_NAME = "cpi_iflows"


class RAGManager:
    """
    Wrapper sobre ChromaDB para indexar y consultar iFlows de SAP CPI.

    Uso:
        rag = get_rag()
        rag.upsert(iflow_id, document_text, metadata_dict)
        similares = rag.get_similar("SOAP invoice integration", n=3)
    """

    def __init__(self):
        os.makedirs(RAG_DIR, exist_ok=True)
        self._client     = chromadb.PersistentClient(path=RAG_DIR)
        self._ef         = DefaultEmbeddingFunction()
        self._collection = self._get_or_create()

    # ------------------------------------------------------------------
    def _get_or_create(self):
        return self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    def count(self) -> int:
        """Retorna el número de iFlows indexados."""
        return self._collection.count()

    # ------------------------------------------------------------------
    def clear(self):
        """Borra todos los vectores y recrea la colección vacía."""
        try:
            self._client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        self._collection = self._get_or_create()

    # ------------------------------------------------------------------
    def upsert(self, iflow_id: str, document: str, metadata: dict):
        """
        Inserta o actualiza un iFlow en el índice.
        metadata solo puede contener valores str, int, float o bool.
        """
        # Sanitizar metadata — ChromaDB rechaza None y tipos compuestos
        clean = {}
        for k, v in metadata.items():
            if isinstance(v, (str, int, float, bool)):
                clean[k] = v
            elif v is None:
                clean[k] = ""
            else:
                clean[k] = str(v)

        self._collection.upsert(
            ids=[iflow_id],
            documents=[document],
            metadatas=[clean],
        )

    # ------------------------------------------------------------------
    def query(self, text: str, n_results: int = 5) -> dict:
        """
        Búsqueda semántica. Retorna el dict crudo de ChromaDB.
        Ajusta n_results si hay menos documentos que el pedido.
        """
        n = min(n_results, max(1, self._collection.count()))
        return self._collection.query(
            query_texts=[text],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )

    # ------------------------------------------------------------------
    def get_similar(self, text: str, n: int = 3) -> list:
        """
        Retorna los N iFlows más similares semánticamente.
        Formato de cada resultado:
          {
            iflow_id, name, package_name, adapter_types,
            distancia (0=idéntico, 2=opuesto),
            resumen (primeros 300 chars del documento)
          }
        """
        if self._collection.count() == 0:
            return []

        results = self.query(text, n_results=n)
        similares = []
        for i, iflow_id in enumerate(results["ids"][0]):
            meta    = results["metadatas"][0][i]
            dist    = round(results["distances"][0][i], 4)
            doc     = results["documents"][0][i][:300]
            similares.append({
                "iflow_id":     iflow_id,
                "name":         meta.get("name", iflow_id),
                "package_name": meta.get("package_name", ""),
                "adapter_types":meta.get("adapter_types", ""),
                "n_scripts":    meta.get("n_scripts", 0),
                "n_mappings":   meta.get("n_mappings", 0),
                "distancia":    dist,
                "resumen":      doc,
            })
        return similares


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------
_rag_instance: RAGManager | None = None


def get_rag() -> RAGManager:
    """Retorna la instancia singleton de RAGManager."""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = RAGManager()
    return _rag_instance
