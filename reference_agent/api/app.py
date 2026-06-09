from fastapi import FastAPI

from reference_agent.api.routes import router as reference_router


app = FastAPI(title="CADly Agent Server")
app.include_router(reference_router)


@app.get("/")
def root():
    return {"message": "CADly Reference Agent server is running."}
