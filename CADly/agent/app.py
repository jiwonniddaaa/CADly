from fastapi import FastAPI
from CADly.agent.routes import router

app = FastAPI(title="CADly Agent Server")
app.include_router(router)

@app.get("/")
def root():
    return {"message": "CADly Agent server is running."}