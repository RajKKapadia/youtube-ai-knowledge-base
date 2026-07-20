import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Video, VideoChunk
from app.services.chunking import chunk_segments
from app.services.embeddings import embed_passages
from app.services.transcription import transcribe_audio
from app.services.vector_store import delete_video_vectors, upsert_chunk_vectors
from app.services.youtube import download_youtube_audio


logger = logging.getLogger(__name__)


def update_status(
    db: Session,
    video: Video,
    status: str,
    progress: int,
    error_message: str | None = None,
) -> None:
    logger.info("Video %s -> status=%s progress=%s", video.id, status, progress)
    video.status = status
    video.progress = progress
    video.error_message = error_message
    db.add(video)
    db.commit()


def process_video_pipeline(db: Session, video_id: uuid.UUID) -> None:
    video = db.get(Video, video_id)
    if video is None:
        raise RuntimeError(f"Video {video_id} not found")

    try:
        update_status(db, video, "downloading", 10)

        downloaded = download_youtube_audio(
            video_id=str(video.id),
            youtube_url=video.youtube_url,
        )

        video.title = downloaded.title
        video.channel_name = downloaded.channel_name
        video.duration = downloaded.duration
        db.commit()

        update_status(db, video, "transcribing", 30)

        segments = transcribe_audio(downloaded.audio_path)
        if not segments:
            raise RuntimeError("No speech segments were produced by transcription.")

        update_status(db, video, "chunking", 60)

        chunks = chunk_segments(
            segments=segments,
            chunk_size=settings.chunk_size_segments,
            overlap=settings.chunk_overlap_segments,
        )
        if not chunks:
            raise RuntimeError("No transcript chunks were created.")

        # Make reprocessing idempotent for this simple demo.
        delete_video_vectors(str(video.id))
        db.execute(delete(VideoChunk).where(VideoChunk.video_id == video.id))
        db.commit()

        chunk_rows: list[VideoChunk] = []
        for chunk in chunks:
            chunk_rows.append(
                VideoChunk(
                    video_id=video.id,
                    chunk_index=chunk.chunk_index,
                    segment_start_index=chunk.segment_start_index,
                    segment_end_index=chunk.segment_end_index,
                    start_time=chunk.start_time,
                    end_time=chunk.end_time,
                    text=chunk.text,
                )
            )

        db.add_all(chunk_rows)
        db.commit()

        update_status(db, video, "embedding", 75)

        vectors = embed_passages([chunk.text for chunk in chunk_rows])

        qdrant_chunks = [
            {
                "id": str(chunk.id),
                "chunk_index": chunk.chunk_index,
                "start_time": chunk.start_time,
                "end_time": chunk.end_time,
                "text": chunk.text,
            }
            for chunk in chunk_rows
        ]

        upsert_chunk_vectors(
            video_id=str(video.id),
            chunks=qdrant_chunks,
            vectors=vectors,
        )

        update_status(db, video, "completed", 100)

        # Audio is no longer needed after transcript + vectors are stored.
        video_dir = Path(settings.data_dir) / str(video.id)
        if video_dir.exists():
            shutil.rmtree(video_dir, ignore_errors=True)

    except Exception as exc:
        db.rollback()
        video = db.get(Video, video_id)
        if video is not None:
            update_status(
                db,
                video,
                "failed",
                video.progress,
                error_message=str(exc),
            )
        raise
