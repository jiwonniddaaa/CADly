from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.routes import router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(router)

app.mount('/static/raw', StaticFiles(directory=settings.raw_storage_path), name='raw')

@app.get('/health')
def health():
    return {'status': 'ok', 'app': settings.app_name, 'env': settings.app_env}
