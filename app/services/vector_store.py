from functools import lru_cache

from qdrant_client import QdrantClient, models

from app.config import settings


@lru_cache
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection() -> None:
    client = get_qdrant_client()

    if client.collection_exists(settings.qdrant_collection):
        return

    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=models.VectorParams(
            size=settings.embedding_dimension,
            distance=models.Distance.COSINE,
        ),
    )


def upsert_chunk_vectors(
    video_id: str,
    chunks: list[dict],
    vectors: list[list[float]],
) -> None:
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors must have the same length")

    ensure_collection()
    client = get_qdrant_client()

    points = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        points.append(
            models.PointStruct(
                id=chunk["id"],
                vector=vector,
                payload={
                    "video_id": video_id,
                    "chunk_id": chunk["id"],
                    "chunk_index": chunk["chunk_index"],
                    "start_time": chunk["start_time"],
                    "end_time": chunk["end_time"],
                    "text": chunk["text"],
                },
            )
        )

    if points:
        client.upsert(
            collection_name=settings.qdrant_collection,
            points=points,
            wait=True,
        )


def query_video_vectors(
    video_id: str,
    query_vector: list[float],
    limit: int,
):
    ensure_collection()
    client = get_qdrant_client()

    response = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="video_id",
                    match=models.MatchValue(value=video_id),
                )
            ]
        ),
        limit=limit,
        with_payload=True,
    )

    return response.points


def delete_video_vectors(video_id: str) -> None:
    client = get_qdrant_client()

    if not client.collection_exists(settings.qdrant_collection):
        return

    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="video_id",
                        match=models.MatchValue(value=video_id),
                    )
                ]
            )
        ),
        wait=True,
    )
