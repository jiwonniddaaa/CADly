from app.connectors.base import BaseConnector
from app.models.schemas import IngestRecord

class PinterestConnector(BaseConnector):
    source_name = 'pinterest'

    async def fetch(self, keyword: str, limit: int = 10) -> list[IngestRecord]:
        return [
            IngestRecord(
                source=self.source_name,
                external_id=f'{keyword}-{i}',
                title=f'Pinterest placeholder result {i} for {keyword}',
                description='Pinterest는 운영 전 공식 API/약관 검토 후 커넥터를 구현하세요.',
                metadata={'keyword': keyword, 'connector': 'placeholder', 'status': 'not_implemented'}
            )
            for i in range(1, limit + 1)
        ]
