from collections import defaultdict
from app.services.embedding import EmbeddingService
from app.services.qdrant_store import QdrantStore
from app.models.schemas import SearchRequest, SearchResultItem, SearchResponse
from app.utils.image_url import to_image_url

class RetrievalService:
    def __init__(self):
        self.embed = EmbeddingService()
        self.store = QdrantStore()

    def search(self, req: SearchRequest, rewritten_query: str | None = None) -> SearchResponse:
        q = rewritten_query or req.query
        tvec = self.embed.embed_text(q)
        cvec = self.embed.embed_clip_text(q)
        svec = self.embed.sparse_from_text(q)

        dense_hits = self.store.query_dense('text_dense', tvec, req.top_k)
        clip_hits = self.store.query_dense('clip_text_dense', cvec, req.top_k)
        sparse_hits = self.store.query_sparse(svec, req.top_k)

        image_hits = []
        if req.image_path:
            ivec = self.embed.embed_image(req.image_path)
            if ivec:
                image_hits = self.store.query_dense('image_dense', ivec, req.top_k)

        acc = defaultdict(lambda: {'score': 0.0, 'payload': None})

        for weight, hits in [(0.45, dense_hits), (0.25, clip_hits), (0.20, sparse_hits), (0.10, image_hits)]:
            for rank, h in enumerate(hits, start=1):
                acc[str(h.id)]['score'] += weight * (1.0 / rank)
                acc[str(h.id)]['payload'] = h.payload

        ranked = sorted(acc.items(), key=lambda x: x[1]['score'], reverse=True)[:req.top_k]

        items = []
        for pid, val in ranked:
            p = val['payload'] or {}
            image_path = p.get('image_path')
            items.append(SearchResultItem(
                id=pid,
                score=round(val['score'], 6),
                title=p.get('title', ''),
                source=p.get('source', ''),
                page_url=p.get('page_url'),
                image_path=image_path,
                image_url=to_image_url(image_path),
                summary=p.get('description') or p.get('caption'),
                metadata={k: v for k, v in p.items() if k not in {'title', 'source', 'page_url', 'image_path', 'description'}}
            ))

        return SearchResponse(query=req.query, rewritten_query=rewritten_query, items=items)
