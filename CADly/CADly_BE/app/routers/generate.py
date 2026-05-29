import base64
from fastapi import APIRouter, HTTPException
from app.services.agent_service import generate_cad_output

router = APIRouter()

@router.post("/{project_id}")
async def generate_cad(project_id: str, request: dict): 
    try:
        # 1. 서비스 계층 호출 (AI 에이전트 도면 생성 로직)
        # file_data = await generate_cad_output(project_data=request)
        
        # [설명] AI 에이전트가 아래와 같은 데이터를 반환했다고 가정합니다.
        # 실제 연동 시에는 file_data에서 아래 값들을 추출하여 매핑해주세요.
        
        # 캔버스에 직접 그릴 SVG (텍스트)
        svg_string = """
        <svg width="100%" height="100%" viewBox="0 0 800 400" xmlns="http://www.w3.org/2000/svg">
            <rect x="50" y="50" width="700" height="300" fill="none" stroke="#3b82f6" stroke-width="4" stroke-dasharray="10,5"/>
            <line x1="50" y1="200" x2="750" y2="200" stroke="#3b82f6" stroke-width="2"/>
            <text x="400" y="190" fill="#3b82f6" text-anchor="middle" font-family="monospace" font-size="20">FLOOR PLAN SECTION</text>
        </svg>
        """
        
        # 다운로드용 DXF 데이터 (바이너리를 Base64 문자열로 인코딩하여 전송)
        # 실제: dxf_base64 = base64.b64encode(file_data["dxf_bytes"]).decode('utf-8')
        dxf_base64 = base64.b64encode(b"dummy dxf content here").decode('utf-8')

        # 2. JSON 형태로 프론트엔드에 전달
        return {
            "success": True,
            "filename": "Urban_Cabin_V4",
            "svg_content": svg_string,
            "dxf_content": dxf_base64
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"CAD 파일 생성 중 서버 오류가 발생했습니다: {str(e)}"
        )