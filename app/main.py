from fastapi import FastAPI

from app.api.routes.videos import router as videos_router
from app.config import settings


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Turn YouTube videos into a timestamped, searchable AI knowledge base."
    ),
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(videos_router)
