from fastapi import APIRouter
from app.agents.reference_agent import ReferenceAgent
from app.models.schemas import SearchRequest, SearchResponse, IngestRecord, CsvPathIngestRequest
from app.services.csv_ingestion import CsvIngestionService
from app.services.ingestion import IngestionService
from app.services.retrieval import RetrievalService

router = APIRouter()
retrieval = RetrievalService()
ingestion = IngestionService()
csv_ingestion = CsvIngestionService()
agent = ReferenceAgent()

@router.post('/reference/search', response_model=SearchResponse)
def reference_search(req: SearchRequest):
    return retrieval.search(req)

@router.post('/reference/ingest/local')
def reference_ingest_local(rec: IngestRecord):
    pid = ingestion.ingest_record(rec)
    return {'status': 'ingested', 'id': pid}

@router.post('/reference/ingest/csv-path')
def reference_ingest_csv_path(req: CsvPathIngestRequest):
    return csv_ingestion.ingest_csv(req.csv_path)

@router.post('/reference/agent/query')
def reference_agent_query(req: SearchRequest):
    return agent.run(req)
