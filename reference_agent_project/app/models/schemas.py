from typing import Any, Optional
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    query: str
    image_path: Optional[str] = None
    top_k: int = Field(default=8, ge=1, le=50)

class SearchResultItem(BaseModel):
    id: str
    score: float
    title: str
    source: str
    page_url: Optional[str] = None
    image_path: Optional[str] = None
    image_url: Optional[str] = None
    summary: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class SearchResponse(BaseModel):
    query: str
    rewritten_query: Optional[str] = None
    items: list[SearchResultItem]

class IngestRecord(BaseModel):
    source: str
    external_id: str
    title: str
    description: str = ''
    page_url: Optional[str] = None
    image_path: Optional[str] = None
    floorplan_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class CsvPathIngestRequest(BaseModel):
    csv_path: str

class AgentQueryResponse(BaseModel):
    rewritten_query: str
    rationale: str
    references: list[SearchResultItem]
