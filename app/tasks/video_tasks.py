import uuid

from app.celery_app import celery_app
from app.database import SessionLocal
from app.services.processing import process_video_pipeline


@celery_app.task(name="process_video")
def process_video(video_id: str) -> None:
    db = SessionLocal()
    try:
        process_video_pipeline(
            db=db,
            video_id=uuid.UUID(video_id),
        )
    finally:
        db.close()
