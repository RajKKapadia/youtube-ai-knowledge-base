import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class VideoCreate(BaseModel):
    youtube_url: HttpUrl


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    youtube_url: str
    title: str | None
    channel_name: str | None
    duration: float | None
    status: str
    progress: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class VideoCreateResponse(BaseModel):
    video_id: uuid.UUID
    status: str
    message: str


class VideoStatusResponse(BaseModel):
    video_id: uuid.UUID
    status: str
    progress: int
    error_message: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    chunk_index: int
    text: str
    start_time: float
    end_time: float
    score: float
    source_url: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class ChatResponse(BaseModel):
    answer: str
    sources: list[SearchResult]
