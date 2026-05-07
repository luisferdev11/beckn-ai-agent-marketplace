"""
Discovery Service — local DS for the Beckn AI Agent Marketplace.

Receives signed `discover` requests from BAPs (via ONIX-BAP routing) and
fans them out to every registered BPP receiver. Each BPP processes the
discover independently and sends its `on_discover` callback back to the
originating BAP via the standard ONIX path — the DS is only involved on
the request path, not on the callback path.

This is a stand-in for the production Discovery Service hosted by Beckn
One at fabric.nfh.global. The same fan-out shape applies once we move
to the real network; only the BPP registry source changes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import BppEntry, load_bpps
from app.forwarder import fan_out

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discovery")

app = FastAPI(title="Beckn Discovery Service", version="1.0.0")

# Loaded once at startup. Tests override via dependency or by replacing _BPPS.
_BPPS: list[BppEntry] = load_bpps()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ack() -> dict:
    return {"message": {"ack": {"status": "ACK"}}}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "discovery", "time": _now_iso(), "bpps": len(_BPPS)}


@app.get("/bpps")
async def list_bpps():
    return {
        "count": len(_BPPS),
        "bpps": [{"subscriber_id": b.subscriber_id, "name": b.name, "receiver_url": b.receiver_url} for b in _BPPS],
    }


@app.post("/beckn/discover")
async def discover(request: Request, background_tasks: BackgroundTasks):
    """
    Accept a Beckn v2 `discover` and fan it out to every registered BPP.

    Returns ACK synchronously; on_discover callbacks come back asynchronously
    from each BPP directly to the originating BAP via ONIX.
    """
    body = await request.json()
    context = body.get("context", {})
    txn_id = context.get("transactionId", "unknown")
    logger.info("discover received [txn=%s] — fanning out to %d BPPs", txn_id[:8] if txn_id else "?", len(_BPPS))

    headers = {k: v for k, v in request.headers.items() if k.lower() in ("authorization", "x-gateway-authorization", "content-type")}

    background_tasks.add_task(fan_out, list(_BPPS), body, headers)

    return JSONResponse(_ack())
