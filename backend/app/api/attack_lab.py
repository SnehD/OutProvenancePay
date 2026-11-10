"""Attack Lab endpoints. Results come from executing the scenarios; nothing is precomputed."""
from __future__ import annotations

import threading

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services import attack_lab as lab

router = APIRouter(prefix="/api/attack-lab", tags=["attack-lab"])

# Each run builds a whole disposable app, and these endpoints have no authentication in this prototype.
# One run at a time keeps repeated calls from piling up (a cheap guard against accidental or deliberate overload).
_busy = threading.Lock()
BUSY = JSONResponse(status_code=429, content={"error": "ATTACK_LAB_BUSY",
                                              "message": "Another Attack Lab run is in progress. Try again in a moment."})


@router.get("/scenarios")
def scenarios() -> dict:
    return {"scenarios": lab.SCENARIOS, "sandbox_notice": lab.SANDBOX_NOTICE}


@router.post("/run/{scenario_id}")
def run(scenario_id: str):
    if scenario_id not in lab.RUNNERS:
        return JSONResponse(status_code=404, content={"error": "NOT_FOUND", "message": "Unknown scenario."})
    if not _busy.acquire(blocking=False):
        return BUSY
    try:
        return lab.run_scenario(scenario_id)
    finally:
        _busy.release()


@router.post("/run-all")
def run_all():
    if not _busy.acquire(blocking=False):
        return BUSY
    try:
        results = [lab.run_scenario(s["id"]) for s in lab.SCENARIOS]
    finally:
        _busy.release()
    return {"results": results, "passed": sum(r["result"] == "PASS" for r in results), "total": len(results),
            "sandbox_notice": lab.SANDBOX_NOTICE}
