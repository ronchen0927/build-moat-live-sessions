# Complete Answers

This folder contains two complete implementations of the same Knowledge Base Q&A Bot:

| Strategy | Folder | Retrieval Layer |
|----------|--------|-----------------|
| Markdown KB | `markdown_kb/` | Section-level Markdown index + BM25 keyword search |
| Vector RAG | `vector_rag/` | Markdown chunks + OpenAI embeddings + FAISS vector search |

Run either implementation from its folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Both implementations read the shared sample docs from `../../docs/`.

Both implementations require an OpenAI API key for answer generation:

```bash
export OPENAI_API_KEY="sk-..."
```

The Markdown KB implementation only needs the key for `/chat`. The Vector RAG implementation also uses the key for embeddings during `/index` and for embedding each `/chat` query.

The Markdown KB implementation also writes an inspectable index file:

```text
.kb/index.json
```

Open it after `POST /index` to see the generated section records and tokens. On server startup, the Markdown KB implementation loads `.kb/index.json` back into memory if the file exists.

The Vector RAG implementation writes a persisted FAISS index:

```text
.kb/faiss_index/
```

Open `.kb/faiss_index/metadata.json` after `POST /index` to see the embedding model and index counts. On server startup, the Vector RAG implementation loads `.kb/faiss_index/` back into memory if the FAISS files exist. Re-run `POST /index` after changing `docs/*.md`.

## Stretch Goals

The complete answers intentionally keep `/chat` non-streaming so the core retrieval logic stays easy to inspect.

Pick one or more extensions after the core retrieval flow works.

### Score Threshold and Fallback

Add a score threshold so weak retrieval results become an explicit fallback instead of a weak answer.

### Streaming Interface

Add:

```text
POST /chat/stream
```

Use Server-Sent Events (SSE) and stream:

1. `sources` event with selected `filename#heading` references
2. `token` events for answer text
3. `done` event when generation finishes

For FastAPI, this can be implemented with `StreamingResponse` and an async generator. For LangChain, use a streaming chat model callback or stream API depending on the model wrapper.

### Browser UI

Build a tiny browser UI over `/chat` or `/chat/stream`. Show selected sources before answer text.

### Multi-Format Import

Add a normalization pipeline:

```text
raw/*.txt or raw/*.html -> docs/*.md -> retrieval index
```

Keep Markdown as the canonical format. The retrieval layer should index normalized Markdown, not parse arbitrary raw files during every query.

### Alternative Interfaces

Wrap the same retrieval core with another interface:

```text
CLI: kb index / kb ask
MCP: expose index, search, and chat as agent tools
Web UI: simple chat screen over /chat or /chat/stream
```

### Wiki Index Generation

Generate `wiki/index.md` from `.kb/index.json` so humans and agents can browse the available topics.

### Answer Filing

Write useful Q&A results back into `wiki/` after review while preserving source citations.

### Conversation Memory

Add short conversation memory for follow-up questions without letting memory override retrieved sources.

### Paraphrase Comparison

Create paraphrased queries and compare Markdown KB vs Vector RAG retrieval quality.
