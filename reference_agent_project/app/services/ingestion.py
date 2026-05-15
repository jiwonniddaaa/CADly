import hashlib
from app.models.schemas import IngestRecord
from app.services.embedding import EmbeddingService
from app.services.metadata_store import MetadataStore
from app.services.qdrant_store import QdrantStore

class IngestionService:
    def __init__(self):
        self.embed = EmbeddingService()
        self.meta = MetadataStore()
        self.store = QdrantStore()
        self.store.ensure_collection()

    def build_search_text(self, rec: IngestRecord) -> str:
        parts = [rec.title, rec.description]
        if rec.metadata.get('search_text'):
            parts.append(str(rec.metadata['search_text']))
        for k, v in rec.metadata.items():
            if k == 'search_text':
                continue
            if isinstance(v, list):
                parts.append(f'{k}: ' + ' '.join(map(str, v)))
            else:
                parts.append(f'{k}: {v}')
        return ' '.join([str(x) for x in parts if x]).strip()

    def ingest_record(self, rec: IngestRecord) -> str:
        merged = self.build_search_text(rec)
        text_dense = self.embed.embed_text(merged)
        clip_text_dense = self.embed.embed_clip_text(merged)
        text_sparse = self.embed.sparse_from_text(merged)
        image_dense = self.embed.embed_image(rec.image_path) if rec.image_path else None
        point_id = hashlib.sha1(f'{rec.source}:{rec.external_id}'.encode()).hexdigest()
        self.meta.upsert(rec)
        self.store.upsert_reference(point_id, rec, text_dense, clip_text_dense, text_sparse, image_dense)
        return point_id
