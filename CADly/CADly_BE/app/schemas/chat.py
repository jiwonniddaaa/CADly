from pydantic import BaseModel
from typing import List, Optional

# 프론트엔드 -> 백엔드 (채팅 요청)
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None

# 백엔드 -> 프론트엔드 (채팅 응답)
class ChatResponse(BaseModel):
    response: str
    image_urls: List[str] = []
    cad_svg_content: Optional[str] = None
    
# 프론트엔드 -> 백엔드 (3D 파일 생성 요청)
class Generate3DRequest(BaseModel):
    project_id: str
    format: str