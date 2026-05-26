import os
import time

from fastapi import FastAPI

from app.routes import router as planner_router

app = FastAPI(
    title="AI Agent Planner",
    version="1.0.0",
    description="Decomposes user prompts into skill-based execution plans",
)

app.include_router(planner_router)

START_TIME = time.time()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": os.getenv("SERVICE_NAME", "planner"),
        "version": os.getenv("PLANNER_VERSION", "1.0.0"),
        "uptime_seconds": int(time.time() - START_TIME),
    }
