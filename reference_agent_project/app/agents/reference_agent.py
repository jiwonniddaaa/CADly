from langchain_anthropic import ChatAnthropic
from app.core.config import settings
from app.models.schemas import SearchRequest, AgentQueryResponse
from app.services.retrieval import RetrievalService

SYSTEM_PROMPT = (
    'You are a reference retrieval agent for an architectural design platform. '
    'Rewrite user queries into concise architectural retrieval language and explain why the results are useful.'
)

class ReferenceAgent:
    def __init__(self):
        self.llm = ChatAnthropic(model=settings.anthropic_model, api_key=settings.anthropic_api_key, temperature=0.2, max_tokens=800)
        self.retrieval = RetrievalService()

    def rewrite_query(self, query: str) -> str:
        prompt = (
            'Rewrite the following user query into a compact English architectural search query. '
            'Include style, program, massing, facade, floor plan, site response keywords when relevant. ' +
            f'User query: {query}. Only output the rewritten query.'
        )
        msg = self.llm.invoke(prompt)
        return getattr(msg, 'content', str(msg)).strip()

    def summarize(self, original_query: str, rewritten_query: str, raw_items: list[dict]) -> tuple[str, str]:
        prompt = (
            f'Original query: {original_query}\n' +
            f'Rewritten query: {rewritten_query}\n' +
            f'Results: {raw_items}\n' +
            'Write one sentence on why this set is relevant, then one compact paragraph summarizing item usefulness.'
        )
        msg = self.llm.invoke([('system', SYSTEM_PROMPT), ('human', prompt)])
        txt = getattr(msg, 'content', str(msg)).strip()
        parts = txt.split('\n', 1)
        rationale = parts[0].strip()
        notes = parts[1].strip() if len(parts) > 1 else txt
        return rationale, notes

    def run(self, req: SearchRequest) -> AgentQueryResponse:
        rewritten = self.rewrite_query(req.query)
        resp = self.retrieval.search(req, rewritten_query=rewritten)
        raw = [i.model_dump() for i in resp.items]
        rationale, notes = self.summarize(req.query, rewritten, raw)
        for item in resp.items:
            item.summary = f"{item.summary or ""} {notes}".strip()
        return AgentQueryResponse(rewritten_query=rewritten, rationale=rationale, references=resp.items)
