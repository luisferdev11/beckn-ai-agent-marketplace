import os
import time

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="AI Agents Service",
    version="2.0.0",
    description="Sample agents for local testing",
)

START_TIME = time.time()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": os.getenv("SERVICE_NAME", "agents"),
        "uptime_seconds": int(time.time() - START_TIME),
    }
