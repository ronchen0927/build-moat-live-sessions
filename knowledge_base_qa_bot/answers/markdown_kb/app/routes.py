from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse

from .indexer import build_index
from .retrieval import query, stream_query
from .schemas import ChatRequest, ChatResponse, IndexResponse

router = APIRouter()

DEMO_PAGE = Path(__file__).resolve().parent / "demo.html"


@router.get("/")
def demo_page():
    return FileResponse(DEMO_PAGE)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/index", response_model=IndexResponse)
def index_docs():
    files_count, sections_count = build_index()
    return IndexResponse(files_indexed=files_count, sections_indexed=sections_count)


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    return query(req.query)


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    return StreamingResponse(
        stream_query(req.query),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
