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

# TODO: Configure chunking parameters for traditional RAG.
#
# Design decision: Balance semantic recall against context noise.
#
# Hints:
# 1. chunk_size around 500 chars is a reasonable prototype default.
# 2. chunk_overlap helps avoid cutting facts at boundaries.
# 3. separators should prefer Markdown structure before individual words.
splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
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
    text = path.read_text(encoding="utf-8")
    filename = path.name
    docs: list[Document] = []
    heading_stack: list[tuple[int, str]] = []
    current_heading: str | None = None
    content_lines: list[str] = []

    def flush():
        nonlocal current_heading, content_lines
        if current_heading is None:
            return
        content = "\n".join(content_lines).strip()
        heading_path = [h for _, h in heading_stack]
        source_id = f"{filename}#{slugify(current_heading)}"
        page_content = " > ".join(heading_path) + ("\n\n" + content if content else "")
        docs.append(Document(
            page_content=page_content,
            metadata={
                "source": source_id,
                "heading": " > ".join(heading_path),
                "file": filename,
            },
        ))
        content_lines = []

    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            heading_text = m.group(2)
            heading_stack = [(l, h) for l, h in heading_stack if l < level]
            heading_stack.append((level, heading_text))
            current_heading = heading_text
        else:
            content_lines.append(line)

    flush()
    return docs


def build_index(docs_dir: Path = DOCS_DIR) -> tuple[int, int]:
    global vectorstore, files_indexed, sections_indexed

    vectorstore = None
    files_indexed = 0
    sections_indexed = 0

    md_files = sorted(docs_dir.glob("*.md"))
    all_docs: list[Document] = []
    for path in md_files:
        all_docs.extend(load_markdown_sections(path))

    files_indexed = len(md_files)

    if not all_docs:
        save_vector_index()
        return files_indexed, sections_indexed

    chunks = splitter.split_documents(all_docs)
    sections_indexed = len(chunks)
    vectorstore = FAISS.from_documents(chunks, get_embeddings())
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


def load_vector_index(index_dir: Path = INDEX_DIR) -> tuple[int, int]:
    global vectorstore, files_indexed, sections_indexed
    if not (index_dir / "index.faiss").exists() or not (index_dir / "index.pkl").exists():
        return 0, 0
    metadata_path = index_dir / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("embedding_model") != EMBEDDING_MODEL:
            return 0, 0
        files_indexed = metadata.get("files_indexed", 0)
        sections_indexed = metadata.get("sections_indexed", 0)
    vectorstore = FAISS.load_local(
        str(index_dir),
        get_embeddings(),
        allow_dangerous_deserialization=True,
    )
    return files_indexed, sections_indexed


def search(query: str, k: int = 3) -> list[tuple[Document, float]]:
    if vectorstore is None:
        return []
    return vectorstore.similarity_search_with_score(query, k=k)
