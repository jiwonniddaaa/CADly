import json
import sqlite3
from pathlib import Path
from app.core.config import settings
from app.models.schemas import IngestRecord

class MetadataStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.sqlite_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init(self):
        sql = """
        create table if not exists references_meta (
            id integer primary key autoincrement,
            source text not null,
            external_id text not null,
            title text not null,
            description text,
            page_url text,
            image_path text,
            floorplan_path text,
            metadata_json text,
            unique(source, external_id)
        )
        """
        with self._conn() as conn:
            conn.execute(sql)
            conn.commit()

    def upsert(self, rec: IngestRecord):
        sql = """
        insert into references_meta (
            source, external_id, title, description, page_url, image_path, floorplan_path, metadata_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(source, external_id) do update set
            title=excluded.title,
            description=excluded.description,
            page_url=excluded.page_url,
            image_path=excluded.image_path,
            floorplan_path=excluded.floorplan_path,
            metadata_json=excluded.metadata_json
        """
        with self._conn() as conn:
            conn.execute(sql, (rec.source, rec.external_id, rec.title, rec.description, rec.page_url, rec.image_path, rec.floorplan_path, json.dumps(rec.metadata, ensure_ascii=False)))
            conn.commit()
