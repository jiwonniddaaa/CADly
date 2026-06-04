import httpx
from typing import Dict, Any

# 실제 AI 에이전트 서버의 주소로 변경해야 합니다.
AI_AGENT_URL = "http://localhost:8001" 

async def send_to_agent(message: str, session_id: str) -> Dict[str, Any]:
    """일반 채팅 및 2D 도면(SVG 문자열) 생성 요청"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{AI_AGENT_URL}/agent/chat",
            json={"message": message, "session_id": session_id}
        )
        response.raise_for_status()
        return response.json()

async def generate_3d_file(project_id: str, format: str) -> bytes:
    """무거운 3D 파일(바이너리) 생성 요청"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{AI_AGENT_URL}/agent/generate3d",
            json={"project_id": project_id, "format": format}
        )
        response.raise_for_status()
        # JSON이 아닌 원시 바이트(Raw Bytes) 데이터를 그대로 반환
        return response.content