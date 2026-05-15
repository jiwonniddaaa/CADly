from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, SparseVectorParams, PointStruct
from app.core.config import settings
from app.models.schemas import IngestRecord

class QdrantStore:
    def __init__(self):
        self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
        self.collection = settings.qdrant_collection

    def ensure_collection(self, text_dim: int = 384, image_dim: int = 512):
        names = [c.name for c in self.client.get_collections().collections]
        if self.collection in names:
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config={
                'text_dense': VectorParams(size=text_dim, distance=Distance.COSINE),
                'image_dense': VectorParams(size=image_dim, distance=Distance.COSINE),
                'clip_text_dense': VectorParams(size=image_dim, distance=Distance.COSINE),
            },
            sparse_vectors_config={'text_sparse': SparseVectorParams()},
        )

    def upsert_reference(self, point_id: str, rec: IngestRecord, text_dense: list[float], clip_text_dense: list[float], text_sparse: dict, image_dense: Optional[list[float]] = None):
        vectors = {'text_dense': text_dense, 'clip_text_dense': clip_text_dense}
        if image_dense is not None:
            vectors['image_dense'] = image_dense
        payload = {'title': rec.title, 'source': rec.source, 'description': rec.description, 'page_url': rec.page_url, 'image_path': rec.image_path, 'floorplan_path': rec.floorplan_path, **rec.metadata}
        self.client.upsert(collection_name=self.collection, points=[PointStruct(id=point_id, vector=vectors, payload=payload)])
        self.client.update_vectors(collection_name=self.collection, points=[{'id': point_id, 'vector': {'text_sparse': text_sparse}}])

    def query_dense(self, vector_name: str, vector: list[float], top_k: int):
        return self.client.query_points(collection_name=self.collection, using=vector_name, query=vector, limit=top_k, with_payload=True).points

    def query_sparse(self, sparse: dict, top_k: int):
        return self.client.query_points(collection_name=self.collection, using='text_sparse', query=sparse, limit=top_k, with_payload=True).points
