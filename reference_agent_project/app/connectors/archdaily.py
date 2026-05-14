import httpx
from bs4 import BeautifulSoup
from app.connectors.base import BaseConnector
from app.models.schemas import IngestRecord

class ArchDailyConnector(BaseConnector):
    source_name = 'archdaily'

    async def fetch(self, keyword: str, limit: int = 10) -> list[IngestRecord]:
        url = f'https://www.archdaily.com/search/projects/categories/houses?q={keyword}'
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            res.raise_for_status()
        soup = BeautifulSoup(res.text, 'lxml')
        out = []
        for i, a in enumerate(soup.select('a[title]')[:limit], start=1):
            title = a.get('title', '').strip()
            href = a.get('href')
            if not title or not href:
                continue
            if href.startswith('/'):
                href = 'https://www.archdaily.com' + href
            out.append(IngestRecord(
                source=self.source_name,
                external_id=f'{keyword}-{i}',
                title=title,
                description=f'ArchDaily search result for {keyword}',
                page_url=href,
                metadata={'keyword': keyword, 'connector': 'html-search', 'compliance_note': 'check robots and terms before production use'}
            ))
        return out
