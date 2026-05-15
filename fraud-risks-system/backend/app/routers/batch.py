from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks

from app.batch_pipeline import get_last_run_status, run_batch
from app.schemas import BatchStatusResponse

router = APIRouter(prefix="/batch", tags=["batch"])


@router.post("/run", response_model=BatchStatusResponse)
async def trigger_batch(background_tasks: BackgroundTasks):
    """Manually trigger a batch analysis run (runs in background)."""
    background_tasks.add_task(run_batch)
    status = await get_last_run_status()
    return BatchStatusResponse(**{**status, "status": "triggered"})


@router.get("/status", response_model=BatchStatusResponse)
async def batch_status():
    """Get the last batch run status."""
    status = await get_last_run_status()
    return BatchStatusResponse(**status)
