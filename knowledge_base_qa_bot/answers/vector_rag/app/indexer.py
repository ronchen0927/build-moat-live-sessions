import json
import os
import re
import shutil
from pathlib import Path

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings


DOCS_DIR = Path(__file__).resolve().parents[3] / "docs"
INDEX_DIR = Path(__file__).resolve().parents[3] / ".kb" / "faiss_index"
EMBEDDING_MODEL = "text-embedding-3-small"
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100,
    separators=["\n\n", "\n", ". ", " "],
)

vectorstore: FAISS | None = None
_embeddings = None
files_indexed = 0
sections_indexed = 0


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def get_embeddings():
    global _embeddings
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set in the server environment")
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            request_timeout=20,
            max_retries=1,
        )
    return _embeddings


def load_markdown_sections(path: Path) -> list[Document]:
    docs: list[Document] = []
    heading_stack: list[tuple[int, str]] = []
    current_heading = path.stem.replace("_", " ").title()
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        content = "\n".join(current_lines).strip()
        if not content:
            current_lines = []
            return
        heading_path = [title for _, title in heading_stack] or [current_heading]
        section_id = f"{path.name}#{slugify(current_heading)}"
        docs.append(
            Document(
                page_content="\n".join([*heading_path, content]),
                metadata={
                    "source": section_id,
                    "file": path.name,
                    "heading": " > ".join(heading_path),
                },
            )
        )
        current_lines = []

    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            current_heading = match.group(2).strip()
            heading_stack = [(lvl, title) for lvl, title in heading_stack if lvl < level]
            heading_stack.append((level, current_heading))
        else:
            current_lines.append(line)

    flush()
    return docs


def build_index(docs_dir: Path = DOCS_DIR) -> tuple[int, int]:
    global vectorstore, files_indexed, sections_indexed

    print(f"[vector_rag] Reading Markdown docs from {docs_dir}", flush=True)
    markdown_files = sorted(docs_dir.glob("*.md"))
    section_docs: list[Document] = []
    for path in markdown_files:
        print(f"[vector_rag] Loading {path.name}", flush=True)
        section_docs.extend(load_markdown_sections(path))

    print(f"[vector_rag] Splitting {len(section_docs)} sections into chunks", flush=True)
    chunks = splitter.split_documents(section_docs)
    if chunks:
        print(f"[vector_rag] Embedding {len(chunks)} chunks with OpenAI", flush=True)
        vectorstore = FAISS.from_documents(chunks, get_embeddings())
        print("[vector_rag] FAISS index built", flush=True)
    else:
        vectorstore = None

    files_indexed = len(markdown_files)
    sections_indexed = len(chunks)
    save_vector_index()
    return files_indexed, sections_indexed


def save_vector_index(index_dir: Path = INDEX_DIR) -> None:
    if vectorstore is None:
        if index_dir.exists():
            shutil.rmtree(index_dir)
        return

    index_dir.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(index_dir))
    metadata = {
        "embedding_model": EMBEDDING_MODEL,
        "files_indexed": files_indexed,
        "sections_indexed": sections_indexed,
    }
    (index_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"[vector_rag] Saved FAISS index to {index_dir}", flush=True)


def load_vector_index(index_dir: Path = INDEX_DIR) -> tuple[int, int]:
    global vectorstore, files_indexed, sections_indexed

    if not (index_dir / "index.faiss").exists() or not (index_dir / "index.pkl").exists():
        return 0, 0

    metadata = {}
    metadata_path = index_dir / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    stored_model = metadata.get("embedding_model")
    if stored_model and stored_model != EMBEDDING_MODEL:
        raise RuntimeError(
            f"Persisted FAISS index uses {stored_model}, but this server uses {EMBEDDING_MODEL}"
        )

    # FAISS stores Document objects in a local pickle. Only load indexes created by this app.
    vectorstore = FAISS.load_local(
        str(index_dir),
        get_embeddings(),
        allow_dangerous_deserialization=True,
    )
    files_indexed = int(metadata.get("files_indexed", 0))
    sections_indexed = int(metadata.get("sections_indexed", 0))
    print(f"[vector_rag] Loaded persisted FAISS index from {index_dir}", flush=True)
    return files_indexed, sections_indexed


def search(query: str, k: int = 3) -> list[tuple[Document, float]]:
    if vectorstore is None:
        return []
    return vectorstore.similarity_search_with_score(query, k=k)
