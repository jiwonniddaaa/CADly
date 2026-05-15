from pathlib import Path
import pandas as pd
from app.models.schemas import IngestRecord
from app.services.ingestion import IngestionService

CORE_COLUMNS = {
    'source', 'external_id', 'title', 'description', 'page_url', 'image_path', 'floorplan_path'
}

TAG_LIKE_COLUMNS = {
    'tags', 'style', 'house_type', 'spaces', 'materials', 'facade', 'architect', 'country', 'area_m2', 'caption'
}

class CsvIngestionService:
    def __init__(self):
        self.ingestion = IngestionService()

    def _normalize_value(self, v):
        if pd.isna(v):
            return None
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    def _split_tag_string(self, v):
        if not v:
            return []
        if not isinstance(v, str):
            return [str(v)]
        raw = v.replace('|', ',').replace(';', ',')
        return [x.strip() for x in raw.split(',') if x.strip()]

    def row_to_record(self, row: dict, idx: int) -> IngestRecord:
        src = self._normalize_value(row.get('source')) or 'archdaily'
        external_id = self._normalize_value(row.get('external_id')) or f'csv-row-{idx}'
        title = self._normalize_value(row.get('title')) or f'untitled-{idx}'
        description = self._normalize_value(row.get('description')) or ''
        page_url = self._normalize_value(row.get('page_url'))
        image_path = self._normalize_value(row.get('image_path'))
        floorplan_path = self._normalize_value(row.get('floorplan_path'))

        metadata = {}
        for col, value in row.items():
            if col in CORE_COLUMNS:
                continue
            val = self._normalize_value(value)
            if val is None:
                continue
            if col in {'tags', 'spaces', 'materials'}:
                metadata[col] = self._split_tag_string(val)
            else:
                metadata[col] = val

        search_text_parts = [title, description]
        for key in ['tags', 'style', 'house_type', 'spaces', 'materials', 'facade', 'architect', 'country', 'caption']:
            val = metadata.get(key)
            if isinstance(val, list):
                search_text_parts.append(' '.join(val))
            elif val:
                search_text_parts.append(str(val))
        metadata['search_text'] = ' | '.join([x for x in search_text_parts if x])

        return IngestRecord(
            source=src,
            external_id=str(external_id),
            title=str(title),
            description=str(description),
            page_url=page_url,
            image_path=image_path,
            floorplan_path=floorplan_path,
            metadata=metadata,
        )

    def ingest_csv(self, csv_path: str) -> dict:
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f'CSV not found: {csv_path}')
        df = pd.read_csv(path)
        ids = []
        for idx, row in enumerate(df.to_dict(orient='records'), start=1):
            rec = self.row_to_record(row, idx)
            ids.append(self.ingestion.ingest_record(rec))
        return {'status': 'ingested', 'count': len(ids), 'ids': ids[:20]}
