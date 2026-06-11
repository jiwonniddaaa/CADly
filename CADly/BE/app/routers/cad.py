import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.schemas.cad import CadImportRequest, CadImportResponse
from app.services.agent_service import download_dxf_from_agent, import_dxf_to_cad, resolve_session_dxf_path

router = APIRouter()


@router.post("/import", response_model=CadImportResponse)
async def cad_import(request: CadImportRequest):
    import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.schemas.cad import CadImportRequest, CadImportResponse
from app.services.agent_service import download_dxf_from_agent, import_dxf_to_cad, resolve_session_dxf_path

router = APIRouter()


@router.post("/import", response_model=CadImportResponse)
async def cad_import(request: CadImportRequest):
    dxf_path = resolve_session_dxf_path(request.session_id, request.dxf_path)
    if not dxf_path:
        raise HTTPException(
            status_code=422,
            detail="DXF 파일 경로가 없습니다. 도면 생성을 먼저 완료해 주세요.",
        )

    try:
        result = await import_dxf_to_cad(
            dxf_path=dxf_path,
            target_cad=request.target_cad,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent server error: {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Agent server is not reachable.",
        ) from exc

    if not result.get("ok"):
        result["fallback"] = "download_dxf"
    return CadImportResponse(**result)


@router.get("/dxf")
async def download_dxf(
    session_id: str = Query(...),
    dxf_path: str | None = Query(default=None),
):
    resolved = resolve_session_dxf_path(session_id, dxf_path)
    if not resolved:
        raise HTTPException(
            status_code=422,
            detail="DXF 파일 경로가 없습니다.",
        )

    try:
        file_bytes, filename = await download_dxf_from_agent(resolved)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="DXF 파일을 찾을 수 없습니다.") from exc
        raise HTTPException(
            status_code=502,
            detail=f"Agent server error: {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Agent server is not reachable.",
        ) from exc

    return Response(
        content=file_bytes,
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dxf")
async def download_dxf(
    session_id: str = Query(...),
    dxf_path: str | None = Query(default=None),
):
    resolved = resolve_session_dxf_path(session_id, dxf_path)
    if not resolved:
        raise HTTPException(
            status_code=422,
            detail="DXF 파일 경로가 없습니다.",
        )

    try:
        file_bytes, filename = await download_dxf_from_agent(resolved)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="DXF 파일을 찾을 수 없습니다.") from exc
        raise HTTPException(
            status_code=502,
            detail=f"Agent server error: {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Agent server is not reachable.",
        ) from exc

    return Response(
        content=file_bytes,
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
