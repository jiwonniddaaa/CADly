# 사용자가 전송하는 이미지가 있어 이 파일은 사용 X

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

# 프론트엔드 -> 백엔드 (채팅 요청)
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None

# 백엔드 -> 프론트엔드 (채팅 응답)
class ChatResponse(BaseModel):
    message: str
    response: str
    image_urls: List[str] = Field(default_factory=list)
    references: List[Dict[str, Any]] = Field(default_factory=list)
    cad_svg_content: Optional[str] = None
    svg_path: Optional[str] = None
    dxf_path: Optional[str] = None
    design_status: Optional[str] = None
    route: str = ""
    agent_type: str = "agent"
    route_label: str = "에이전트"
    active_orchestrator: str = "planning"
    debug: Optional[Dict[str, Any]] = None
    
# 프론트엔드 -> 백엔드 (3D 파일 생성 요청)
class Generate3DRequest(BaseModel):
    project_id: str
    format: str