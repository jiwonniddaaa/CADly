import httpx
from typing import Dict, Any
from fastapi import UploadFile

# 실제 AI 에이전트 서버의 주소로 변경해야 합니다.
AI_AGENT_URL = "http://localhost:8001" 

async def send_to_agent(message: str, session_id: str, file: UploadFile | None = None) -> Dict[str, Any]:
    """일반 채팅(이미지 첨부 지원) 및 2D 도면(SVG 문자열) 생성 요청"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. 텍스트 데이터 준비
        data = {
            "message": message,
            "session_id": session_id
        }
        
        # 2. 파일 데이터 준비 (첨부된 파일이 있을 경우)
        files_payload = None
        if file:
            content = await file.read()
            files_payload = {"file": (file.filename, content, file.content_type)}
        
        # 3. multipart/form-data 형식으로 AI 에이전트 서버에 전송
        response = await client.post(
            f"{AI_AGENT_URL}/agent/chat",
            data=data,
            files=files_payload
        )
        
        response.raise_for_status()
        return response.json()

async def generate_3d_file(project_id: str, format: str) -> bytes:
    """무거운 3D 파일(바이너리) 생성 요청 (기존 코드 완벽 유지)"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{AI_AGENT_URL}/agent/generate3d",
            json={"project_id": project_id, "format": format}
        )
        response.raise_for_status()
        # JSON이 아닌 원시 바이트(Raw Bytes) 데이터를 그대로 반환
        return response.content