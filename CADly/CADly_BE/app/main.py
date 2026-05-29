from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 분리된 두 개의 라우터를 모두 가져옵니다.
from app.routers.chat import router as chat_router
from app.routers.generate import router as generate_router

app = FastAPI(
    title="CADly AI Gateway Server"
)

# CORS 설정 (React 프론트엔드 연동을 위해 절대 유지)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. 텍스트 기반 채팅 라우터 등록
app.include_router(
    chat_router,
    prefix="/chat",
    tags=["Chatting"]
)

# 2. 파일 생성(Generate) 전용 신규 라우터 등록
app.include_router(
    generate_router,
    prefix="/generate",
    tags=["CAD Generation"]
)

# 기존 Root 상태 확인용 엔드포인트 유지
@app.get("/")
def root():
    return {
        "message": "Gateway server running"
    }