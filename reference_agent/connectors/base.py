from abc import ABC, abstractmethod
from reference_agent.models.schemas import IngestRecord

class BaseConnector(ABC):
    source_name: str

    @abstractmethod
    async def fetch(self, keyword: str, limit: int = 10) -> list[IngestRecord]:
        raise NotImplementedError
