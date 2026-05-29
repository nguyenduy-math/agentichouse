from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.batch_pipeline import get_last_run_status, run_batch
from app.config import settings
from app.database import get_db
from app import ml_trainer
from app.schemas import BatchStatusResponse, FeatureImportance, MLModelStatus, MLTrainResult

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


@router.post("/train", response_model=MLTrainResult)
async def train_ml_model(db: Annotated[AsyncSession, Depends(get_db)]):
    """Manually trigger ML model training on all labeled reviews."""
    label_count = await ml_trainer.count_usable_labels(db)
    if label_count < settings.ml_min_samples:
        from fastapi import HTTPException
        raise HTTPException(
            400,
            f"Not enough labeled reviews to train ({label_count}/{settings.ml_min_samples}). "
            "Label more claims as 'legitimate' or 'confirmed_fraud' first.",
        )

    metadata = await ml_trainer.train_and_save(db, settings.ml_model_path)

    bundle = ml_trainer.load_model(settings.ml_model_path)
    importances = ml_trainer.get_feature_importances(
        bundle["model"], metadata["feature_names"]
    ) if bundle else []

    return MLTrainResult(
        status="trained",
        n_samples=metadata["n_samples"],
        cv_auc=metadata["cv_auc"],
        trained_at=metadata["trained_at"],
        feature_importances=[FeatureImportance(**f) for f in importances],
    )


@router.get("/model-status", response_model=MLModelStatus)
async def ml_model_status(db: Annotated[AsyncSession, Depends(get_db)]):
    """Return ML model training status and metadata."""
    labeled_so_far = await ml_trainer.count_usable_labels(db)
    bundle = ml_trainer.load_model(settings.ml_model_path)

    if bundle is None:
        return MLModelStatus(
            is_trained=False,
            labeled_so_far=labeled_so_far,
            min_samples_needed=settings.ml_min_samples,
        )

    meta = bundle["metadata"]
    importances = ml_trainer.get_feature_importances(bundle["model"], meta["feature_names"])

    return MLModelStatus(
        is_trained=True,
        labeled_so_far=labeled_so_far,
        min_samples_needed=settings.ml_min_samples,
        n_samples=meta.get("n_samples"),
        cv_auc=meta.get("cv_auc"),
        trained_at=meta.get("trained_at"),
        feature_importances=[FeatureImportance(**f) for f in importances[:10]],
    )
