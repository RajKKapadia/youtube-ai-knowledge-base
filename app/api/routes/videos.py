import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Video
from app.schemas import (
    ChatRequest,
    ChatResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    VideoCreate,
    VideoCreateResponse,
    VideoResponse,
    VideoStatusResponse,
)
from app.services.search import search_video
from app.services.vector_store import delete_video_vectors
from app.tasks.video_tasks import process_video


router = APIRouter(prefix="/videos", tags=["videos"])


def get_video_or_404(db: Session, video_id: uuid.UUID) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.post(
    "",
    response_model=VideoCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_video(payload: VideoCreate, db: Session = Depends(get_db)) -> VideoCreateResponse:
    video = Video(
        youtube_url=str(payload.youtube_url),
        status="pending",
        progress=0,
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    process_video.delay(str(video.id))

    return VideoCreateResponse(
        video_id=video.id,
        status=video.status,
        message="Video accepted for background processing.",
    )


@router.get("", response_model=list[VideoResponse])
def list_videos(db: Session = Depends(get_db)) -> list[Video]:
    return list(
        db.scalars(
            select(Video).order_by(Video.created_at.desc())
        ).all()
    )


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(video_id: uuid.UUID, db: Session = Depends(get_db)) -> Video:
    return get_video_or_404(db, video_id)


@router.get("/{video_id}/status", response_model=VideoStatusResponse)
def get_video_status(
    video_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> VideoStatusResponse:
    video = get_video_or_404(db, video_id)
    return VideoStatusResponse(
        video_id=video.id,
        status=video.status,
        progress=video.progress,
        error_message=video.error_message,
    )


@router.post("/{video_id}/search", response_model=SearchResponse)
def search(
    video_id: uuid.UUID,
    payload: SearchRequest,
    db: Session = Depends(get_db),
) -> SearchResponse:
    video = get_video_or_404(db, video_id)
    if video.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Video is not ready. Current status: {video.status}",
        )

    results = search_video(
        video=video,
        query=payload.query,
        top_k=payload.top_k,
    )
    return SearchResponse(query=payload.query, results=results)


@router.post("/{video_id}/chat", response_model=ChatResponse)
def chat(
    video_id: uuid.UUID,
    payload: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    video = get_video_or_404(db, video_id)
    if video.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Video is not ready. Current status: {video.status}",
        )

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "OPENAI_API_KEY is not configured. "
                "The /search endpoint works fully locally; configure an OpenAI key "
                "only if you want generated answers from /chat."
            ),
        )

    sources = search_video(
        video=video,
        query=payload.question,
        top_k=payload.top_k,
    )

    if not sources:
        return ChatResponse(
            answer="I could not find relevant information in this video.",
            sources=[],
        )

    context_parts = []
    for index, source in enumerate(sources, start=1):
        context_parts.append(
            f"[Source {index} | {source.start_time:.2f}s-{source.end_time:.2f}s]\n"
            f"{source.text}"
        )
    context = "\n\n".join(context_parts)

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=settings.openai_model,
        instructions=(
            "Answer the user's question using only the supplied video transcript "
            "context. If the context does not contain the answer, say so. "
            "Be concise and factual."
        ),
        input=(
            f"Question:\n{payload.question}\n\n"
            f"Video transcript context:\n{context}"
        ),
    )

    return ChatResponse(
        answer=response.output_text,
        sources=sources,
    )


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Response:
    video = get_video_or_404(db, video_id)

    delete_video_vectors(str(video.id))

    video_dir = Path(settings.data_dir) / str(video.id)
    if video_dir.exists():
        shutil.rmtree(video_dir, ignore_errors=True)

    db.delete(video)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
