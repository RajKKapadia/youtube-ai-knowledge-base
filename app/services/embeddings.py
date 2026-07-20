from functools import lru_cache

from fastembed import TextEmbedding

from app.config import settings


@lru_cache
def get_embedding_model() -> TextEmbedding:
    return TextEmbedding(
        model_name=settings.embedding_model,
        cache_dir=settings.model_cache_dir,
    )


def embed_passages(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    model = get_embedding_model()
    inputs = [f"passage: {text}" for text in texts]
    return [vector.tolist() for vector in model.embed(inputs)]


def embed_query(text: str) -> list[float]:
    model = get_embedding_model()
    vector = next(model.embed([f"query: {text}"]))
    return vector.tolist()
