# YouTube AI Knowledge Base — FastAPI Backend

A backend-only demo that turns a YouTube video into a timestamped, searchable AI knowledge base.

## Architecture

![YouTube AI Knowledge Base project process](docs/assets/project-process.svg)

The project has two connected paths:

1. **Ingest and index:** `POST /videos` creates a pending PostgreSQL record and
   queues a Celery task through Redis. The worker downloads the audio,
   transcribes it locally, builds overlapping timestamped chunks, embeds them,
   then stores chunk text and metadata in PostgreSQL and searchable vectors in
   Qdrant.
2. **Retrieve and answer:** both `/search` and `/chat` embed the user's query
   locally and retrieve chunks from Qdrant with a `video_id` filter. `/search`
   returns those timestamped results directly. `/chat` optionally sends only the
   retrieved context to the OpenAI Responses API and returns a grounded answer
   with the same sources.

## Services

- **FastAPI** — HTTP API
- **Celery** — background video-processing worker
- **Redis** — Celery broker/result backend
- **PostgreSQL** — videos and transcript chunks
- **Qdrant** — vector database
- **yt-dlp + BgUtils PO-token provider + Deno + FFmpeg** — YouTube audio extraction
- **faster-whisper** — local transcription
- **FastEmbed** — local embeddings
- **OpenAI** — optional generated answer for `/chat`; `/search` does not require it

## Data model

### `videos`

One row per YouTube video.

### `video_chunks`

Many rows per video.

A chunk contains consecutive Whisper segments:

```text
Chunk 0 -> segments 0..9
Chunk 1 -> segments 8..17
Chunk 2 -> segments 16..25
```

For every chunk:

```text
chunk.start_time = first_segment.start
chunk.end_time   = last_segment.end
chunk.text       = combined segment text
```

The 2-segment overlap helps preserve context across chunk boundaries.

Qdrant uses **one collection for all video chunks**. Every vector has `video_id` in its payload, so searches are filtered to the selected video.

---

# Run with Docker

## 1. Requirements

Install:

- Docker
- Docker Compose v2

No local PostgreSQL, Redis, Qdrant, Whisper, or Python environment is required.

## 2. Configure environment

```bash
cp .env.example .env
```

The default setup works without an OpenAI key for ingestion and semantic search.

To enable `/chat`, edit `.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.5
```

## 3. Start everything

```bash
docker compose up --build
```

That single command starts:

- BgUtils PO-token provider
- PostgreSQL
- Redis
- Qdrant
- FastAPI
- Celery worker

Alembic migrations run automatically before the API starts.

The first transcription and first search may take longer because the Whisper
and embedding models are downloaded into the shared `model_cache` Docker volume
at `/tmp/youtube-ai-knowledge-base/models`.

## 4. Open the API docs

Open:

```text
http://localhost:8000/docs
```

Qdrant dashboard:

```text
http://localhost:6333/dashboard
```

The PO-token provider is private to the Compose network. The worker waits for
its health check before it starts processing videos.

---

# Run without Docker

The API and worker are separate processes. A native run therefore needs local
PostgreSQL, Redis, Qdrant, FFmpeg, and the BgUtils PO-token server in addition
to Python.

## 1. Install host requirements

- Python 3.12.11 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- PostgreSQL 16 or newer
- Redis 7 or newer
- [Qdrant](https://qdrant.tech/documentation/guides/installation/)
- FFmpeg
- Git
- Node.js 22 or newer

On Ubuntu or Debian, PostgreSQL, Redis, FFmpeg, and Git can be installed with:

```bash
sudo apt update
sudo apt install postgresql redis-server ffmpeg git
sudo systemctl enable --now postgresql redis-server
```

Install Node.js 22 using your preferred Node version manager or the official
Node.js packages. Install the native Qdrant binary from its releases, extract
it, and start it in a separate terminal:

```bash
./qdrant
```

Qdrant listens on `http://localhost:6333` by default.

## 2. Create the PostgreSQL database

The example environment uses the `postgres` role with password `postgres`:

```bash
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'postgres';"
sudo -u postgres createdb -O postgres youtube_kb
```

Skip the `createdb` command if `youtube_kb` already exists. For a different
role, password, host, or database, update `DATABASE_URL` in `.env`.

## 3. Install the Python environment

From this repository:

```bash
cp .env.example .env
uv sync
```

The example file uses `localhost` for native PostgreSQL, Redis, Qdrant, and the
PO-token server. Docker Compose overrides those hosts with Compose service names
without changing `.env`.

## 4. Build and start the PO-token server

Clone the provider beside this repository so its generated files do not enter
this Git worktree:

```bash
git clone --single-branch --branch 1.3.1 \
  https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
  ../bgutil-ytdlp-pot-provider
cd ../bgutil-ytdlp-pot-provider/server
npm ci
npx tsc
node build/main.js
```

Leave that terminal running. The server listens on `http://127.0.0.1:4416`.
The Python plugin itself is installed by `uv sync`.

## 5. Run database migrations

Back in this repository:

```bash
uv run alembic upgrade head
```

## 6. Start the API

In one terminal:

```bash
uv run run.py
```

The equivalent explicit command is:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 7. Start the worker

In another terminal:

```bash
uv run celery -A app.celery_app.celery_app worker \
  --loglevel=info \
  --concurrency=1
```

The complete native run has six active components: PostgreSQL, Redis, Qdrant,
the PO-token server, and the two application processes (API and worker). Open
`http://localhost:8000/docs`, submit a video, and keep the worker terminal open
to see processing warnings or failures.

---

# API flow

## 1. Submit a YouTube video

```bash
curl -X POST http://localhost:8000/videos \
  -H "Content-Type: application/json" \
  -d '{
    "youtube_url": "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"
  }'
```

Example response:

```json
{
  "video_id": "2bfef150-0198-4c7c-bcdc-244c840f9b91",
  "status": "pending",
  "message": "Video accepted for background processing."
}
```

Save the `video_id`.

## 2. Check status

```bash
curl http://localhost:8000/videos/VIDEO_ID/status
```

Possible states:

```text
pending
downloading
transcribing
chunking
embedding
completed
failed
```

Example:

```json
{
  "video_id": "2bfef150-0198-4c7c-bcdc-244c840f9b91",
  "status": "embedding",
  "progress": 75,
  "error_message": null
}
```

## 3. Search inside the video

Wait until status is `completed`.

```bash
curl -X POST http://localhost:8000/videos/VIDEO_ID/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What does the video say about vector databases?",
    "top_k": 5
  }'
```

Example result:

```json
{
  "query": "What does the video say about vector databases?",
  "results": [
    {
      "chunk_id": "6b81be76-f4b7-4ed0-b54d-f5ac28624175",
      "chunk_index": 7,
      "text": "A vector database stores...",
      "start_time": 510.2,
      "end_time": 575.8,
      "score": 0.86,
      "source_url": "https://www.youtube.com/watch?v=...&t=510s"
    }
  ]
}
```

The returned URL jumps directly to the chunk's start time.

## 4. Chat with the video

Requires `OPENAI_API_KEY`.

```bash
curl -X POST http://localhost:8000/videos/VIDEO_ID/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Summarize how the video explains vector databases.",
    "top_k": 5
  }'
```

The backend:

1. Embeds the question locally.
2. Searches Qdrant for relevant chunks filtered by `video_id`.
3. Sends only the retrieved transcript context to the configured OpenAI model.
4. Returns the generated answer and timestamped source chunks.

## 5. List videos

```bash
curl http://localhost:8000/videos
```

## 6. Delete a video

```bash
curl -X DELETE http://localhost:8000/videos/VIDEO_ID
```

This removes:

- the video row from PostgreSQL
- related chunks via cascade
- matching vectors from Qdrant
- any remaining temporary local audio directory

---

# Important code path: timestamped chunking

The key logic is in:

```text
app/services/chunking.py
```

The flow is:

```python
group = segments[start_index : start_index + chunk_size]

chunk = TranscriptChunk(
    start_time=group[0].start,
    end_time=group[-1].end,
    text=" ".join(segment.text for segment in group),
)
```

With:

```env
CHUNK_SIZE_SEGMENTS=10
CHUNK_OVERLAP_SEGMENTS=2
```

you get:

```text
segments 0..9   -> chunk 0
segments 8..17  -> chunk 1
segments 16..25 -> chunk 2
```

---

# Useful Docker commands

Run in foreground:

```bash
docker compose up --build
```

Run detached:

```bash
docker compose up --build -d
```

Watch API logs:

```bash
docker compose logs -f api
```

Watch processing logs:

```bash
docker compose logs -f worker
```

Stop:

```bash
docker compose down
```

Stop and delete all persisted data/model caches:

```bash
docker compose down -v
```

---

# Configuration notes

## YouTube downloads and PO tokens

YouTube increasingly requires Proof-of-Origin tokens for media transfers. This
project installs the BgUtils yt-dlp plugin and uses the token-backed `mweb`
client by default:

```env
YOUTUBE_PLAYER_CLIENT=mweb
YOUTUBE_POT_PROVIDER_URL=http://127.0.0.1:4416
YOUTUBE_FORMAT=best[acodec!=none][vcodec!=none][height<=360]/bestaudio/best
YOUTUBE_DOWNLOAD_RETRIES=3
```

Docker Compose overrides the provider URL to `http://pot-provider:4416` and
starts the matching `brainicism/bgutil-ytdlp-pot-provider:1.3.1` service.
Native runs must start the provider server as described above.

The format selector prefers a low-resolution progressive stream containing
both audio and video. FFmpeg immediately extracts its audio to WAV. This uses
slightly more bandwidth than an audio-only format, but avoids the audio-only
Google Video URLs that are commonly rejected with HTTP 403; `bestaudio/best`
remains the fallback when a progressive stream is unavailable.

If processing fails at `downloading` with a provider or HTTP 403 warning, check:

```bash
docker compose ps pot-provider
docker compose logs pot-provider worker
```

For a native run, confirm `http://127.0.0.1:4416/ping` is reachable and that the
provider terminal is still running. Personal YouTube cookies are not required
for ordinary public videos and are intentionally not configured.

## Temporary data and model cache

The API and worker use temporary filesystem paths by default:

```env
DATA_DIR=/tmp/youtube-ai-knowledge-base/videos
MODEL_CACHE_DIR=/tmp/youtube-ai-knowledge-base/models
```

`DATA_DIR` holds downloaded audio only while a video is being processed. The
worker removes that video's directory after successful ingestion.
`MODEL_CACHE_DIR` holds the downloaded Whisper and embedding models so later
requests can reuse them.

Docker mounts the shared `video_data` and `model_cache` volumes at these same
paths, allowing the API and worker containers to use consistent storage. The
volumes remain available across container restarts and are removed with:

```bash
docker compose down -v
```

## Whisper

Default:

```env
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

For better transcription quality, try:

```env
WHISPER_MODEL=small
```

or:

```env
WHISPER_MODEL=medium
```

Larger models require more memory and are slower on CPU.

This Compose setup intentionally defaults to CPU so it works with a normal Docker installation. GPU-enabled faster-whisper requires an NVIDIA-compatible container image and NVIDIA Container Toolkit configuration.

## Embeddings

Default:

```env
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSION=384
```

If you change the embedding model to one with a different vector dimension, update `EMBEDDING_DIMENSION` and recreate the Qdrant collection/volume:

```bash
docker compose down -v
docker compose up --build
```
