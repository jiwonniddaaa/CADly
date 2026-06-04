from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.chat import router as chat_router
from app.routers.generate import router as generate_router

app = FastAPI(title="CADly AI Gateway Server")

# CORS 미들웨어 설정 (프론트엔드 React 서버 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 배포 시에는 React 서버 도메인만 기입
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록 (프론트엔드 axios apiClient 설정에 맞춰 prefix 부여)
app.include_router(
    chat_router, 
    prefix="/api/v1/chat", 
    tags=["Chat"]
)

app.include_router(
    generate_router, 
    prefix="/api/v1/generate", 
    tags=["Generation"]
)

@app.get("/")
def root():
    return {"message": "CADly AI Gateway server is running smoothly."}