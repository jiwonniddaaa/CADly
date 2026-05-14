from app.models.schemas import IngestRecord
from app.services.ingestion import IngestionService

samples = [
    IngestRecord(
        source='manual',
        external_id='sample-1',
        title='Minimal Courtyard House',
        description='Compact modern house around a courtyard.',
        metadata={'style': 'minimal', 'country': 'japan', 'tags': ['courtyard', 'minimal', 'lightwell'], 'area_m2': 120}
    ),
    IngestRecord(
        source='manual',
        external_id='sample-2',
        title='Sloped Site Concrete House',
        description='Split-level house on a steep site with exposed concrete.',
        metadata={'style': 'brutalist', 'country': 'korea', 'tags': ['slope', 'split-level', 'concrete'], 'area_m2': 180}
    ),
]

if __name__ == '__main__':
    svc = IngestionService()
    for rec in samples:
        print('ingested', svc.ingest_record(rec), rec.title)
