from app.models import Video
from app.schemas import SearchResult
from app.services.embeddings import embed_query
from app.services.vector_store import query_video_vectors


def add_timestamp_to_youtube_url(url: str, start_time: float) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}t={int(start_time)}s"


def search_video(
    video: Video,
    query: str,
    top_k: int,
) -> list[SearchResult]:
    query_vector = embed_query(query)
    points = query_video_vectors(
        video_id=str(video.id),
        query_vector=query_vector,
        limit=top_k,
    )

    results: list[SearchResult] = []
    for point in points:
        payload = point.payload or {}
        chunk_id = payload.get("chunk_id")
        if not chunk_id:
            continue

        start_time = float(payload.get("start_time", 0.0))
        end_time = float(payload.get("end_time", 0.0))

        results.append(
            SearchResult(
                chunk_id=chunk_id,
                chunk_index=int(payload.get("chunk_index", 0)),
                text=str(payload.get("text", "")),
                start_time=start_time,
                end_time=end_time,
                score=float(point.score),
                source_url=add_timestamp_to_youtube_url(
                    video.youtube_url,
                    start_time,
                ),
            )
        )

    return results
