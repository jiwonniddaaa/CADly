from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    agent_type: str        # 어떤 에이전트(site/reference)인지 구분하는 값
    session_id: str | None = None # 세션 유지용

class ChatResponse(BaseModel):
    response: str