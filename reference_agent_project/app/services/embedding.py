from pathlib import Path
from typing import Optional
import numpy as np
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import CLIPModel, CLIPProcessor
import torch
from app.core.config import settings

class EmbeddingService:
    def __init__(self):
        self.text_model = SentenceTransformer(settings.text_embed_model)
        self.clip_processor = CLIPProcessor.from_pretrained(settings.clip_model)
        self.clip_model = CLIPModel.from_pretrained(settings.clip_model)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.clip_model.to(self.device)

    def embed_text(self, text: str) -> list[float]:
        v = self.text_model.encode(text, normalize_embeddings=True)
        return [float(x) for x in v]

    def embed_clip_text(self, text: str) -> list[float]:
        inputs = self.clip_processor(text=[text], return_tensors='pt', padding=True).to(self.device)
        with torch.no_grad():
            feats = self.clip_model.get_text_features(**inputs)
            feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
        return feats[0].detach().cpu().numpy().astype(np.float32).tolist()

    def embed_image(self, image_path: str) -> Optional[list[float]]:
        path = Path(image_path)
        if not image_path or not path.exists():
            return None
        img = Image.open(path).convert('RGB')
        inputs = self.clip_processor(images=img, return_tensors='pt').to(self.device)
        with torch.no_grad():
            feats = self.clip_model.get_image_features(**inputs)
            feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
        return feats[0].detach().cpu().numpy().astype(np.float32).tolist()

    def sparse_from_text(self, text: str) -> dict:
        tokens = [t.strip(',.()[]{}:;!?').lower() for t in text.split() if t.strip()]
        tf = {}
        for t in tokens:
            if len(t) < 2:
                continue
            tf[t] = tf.get(t, 0) + 1
        terms = sorted(tf)
        return {'indices': [abs(hash(t)) % 1000000 for t in terms], 'values': [float(tf[t]) for t in terms]}
