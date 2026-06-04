from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.schemas.chat import Generate3DRequest
from app.services.agent_service import generate_3d_file

router = APIRouter()

@router.post("/3d")
async def generate_3d(request: Generate3DRequest):
    try:
        # 1. AI 에이전트로부터 바이너리 데이터 수신
        file_bytes = await generate_3d_file(request.project_id, request.format)
        
        # 2. 확장자에 따른 정확한 MIME 타입 지정
        mime_type = "application/octet-stream"
        if request.format == ".3dm":
            mime_type = "model/vnd.3dm" # Rhino
        elif request.format == ".glb":
            mime_type = "model/gltf-binary"
        elif request.format == ".dwg":
            mime_type = "image/vnd.dwg"
            
        # 3. JSON이 아닌 파일(Response) 형식으로 반환 (프론트엔드의 responseType: 'blob'과 매핑)
        return Response(content=file_bytes, media_type=mime_type)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))