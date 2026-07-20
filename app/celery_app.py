from celery import Celery

from app.config import settings


celery_app = Celery(
    "youtube_ai_kb",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.video_tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
