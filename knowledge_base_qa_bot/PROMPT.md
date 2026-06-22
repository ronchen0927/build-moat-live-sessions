# Design a Knowledge Base Q&A Bot

## System Requirements

Build a Q&A bot over a small Markdown knowledge base:

- The repo provides sample `.md` documents in `docs/`
- The system builds an index from those documents
- The Markdown KB strategy should write an inspectable `.kb/index.json`
- The Vector RAG strategy should persist its FAISS index in `.kb/faiss_index/`
- Users ask questions through an API
- Answers must be grounded in the indexed documents
- Answers must cite sources using `filename#heading`
- If the knowledge base does not contain the answer, the system should say it cannot confirm

## Choose a Retrieval Strategy

You can solve this with either strategy:

### Strategy A: Markdown KB

```text
Markdown files -> heading sections -> section index -> BM25 keyword search -> raw Markdown context -> LLM answer
```

This is inspired by the Karpathy-style LLM knowledge base pattern: plain Markdown files, explicit indexes, and LLM-readable context instead of embeddings.

### Strategy B: Vector RAG

```text
Markdown files -> chunks -> embeddings -> vector search -> retrieved context -> LLM answer
```

This is the traditional RAG path: semantic retrieval with embeddings and a vector store.

## Design Questions

Answer these before you start coding:

1. Which retrieval strategy did you choose, and why?
  兩種都可接受，重點是理由要對上題目情境（小型、Markdown、要可檢查、要引用 heading）：
  - 選 Markdown KB（多數人這題會選這個）：因為 KB 很小（10 個檔）、文件本身就是結構化 Markdown、要求 index.json
  可被人眼檢查、引用單位剛好就是 heading。BM25 不需要 embedding、不花錢、可離線、好除錯
  - 選 Vector RAG：如果預期使用者會用同義詞／換句話說問問題（語意檢索贏關鍵字），或之後要擴到大量文件
2. What is the retrieval unit in your design: file, section, or chunk?
  - Markdown KB → section（以 heading 切）。剛好對上引用格式 filename#heading，一個 section 語意完整又不會太長
  - Vector RAG → chunk（section 太長時再切，常見 200–500 token，帶 overlap）
  主流答案：section 是預設，只有當單一 section 太長超過 context 才往下切成 chunk
3. How do you decide what goes into the prompt?
  通用做法：
  - 檢索 → 取 top-k（常見 k=3~5）
  - 加 分數門檻：低於門檻就丟掉（接到第 5 題）
  - 控制 token 預算：照分數排序塞到上限為止
  - 每段帶上來源標記（filename#heading），讓模型能引用
  - system prompt 明確規定：只能用提供的 context 回答，找不到就說無法確認
system prompt 
4. How do you cite sources so users can inspect the original Markdown?
  - 索引時就為每個 section 存 {file, heading, anchor}
  - anchor 用 GitHub 風格的 slug（heading 轉小寫、空白變 -、去標點），組成 refund_policy.md#refund-timeline。
  - 回答時把引用附在後面，使用者可直接開檔跳到該 heading
5. What should happen when retrieval finds weak or irrelevant results?
  - 設分數門檻，最佳結果低於門檻 → 不要硬湊引用，直接回 「無法從知識庫確認」（cannot-confirm）
  - 寧可誠實說不知道，也不要產生沒有出處的幻覺
  - 這正是 Stretch Goal「Score Threshold and Fallback」要的
6. When would you switch from Markdown KB to Vector RAG?
  - 使用者開始用同義詞／自然語言換句話說，BM25 關鍵字對不上（synonym miss）
  - 文件變多，純關鍵字 recall 下降
  - 需要跨語言或語意相似度
7. When would you switch from Vector RAG back to a Markdown index?
  - 規模其實很小、語意檢索是殺雞用牛刀
  - 想要可稽核、可 diff、可人工檢查（embedding 是黑盒，難解釋為何選這段）
  - 想省成本／離線（embedding 每次查詢要花錢、要 API）
  - 出現語意誤命中（semantic false positive）難控管時
8. If the knowledge base grows from 10 files to 100,000 files, what changes?
  - 索引：index.json 全載入記憶體不可行 → 改用真正的搜尋引擎（FAISS/Elasticsearch/向量 DB），改批次／增量索引
  - 檢索：純 BM25 或 brute-force 向量比對撐不住 → 需 ANN 索引、分片（sharding）
  - 架構：索引與查詢服務分離、加快取、加 metadata 過濾先縮小範圍
  - 品質：常走 hybrid（BM25 + 向量）+ re-ranking 的兩階段
  - 維運：增量更新、版本控管、監控檢索品質

## Verification

Before running the server, set your OpenAI API key:

```bash
export OPENAI_API_KEY="sk-..."
```

Both strategies use OpenAI for final answer generation. Vector RAG also uses OpenAI embeddings during `/index` and for each `/chat` query.

Your prototype should pass all of these:

```bash
# Health check
curl http://localhost:8000/health
# -> 200, {"status": "ok"}

# Chat before indexing
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "How long do refunds take?"}'
# -> 200, should indicate the knowledge base has not been indexed yet

# Build the index from docs/*.md
curl -X POST http://localhost:8000/index
# -> 200, returns {"files_indexed": N, "sections_indexed": M}

# Markdown KB only: inspect the generated section index
cat .kb/index.json

# Markdown KB only: restart the server, then ask again without POST /index
# -> should load .kb/index.json on startup

# Vector RAG only: inspect the persisted FAISS index metadata
cat .kb/faiss_index/metadata.json

# Vector RAG only: restart the server, then ask again without POST /index
# -> should load .kb/faiss_index/ on startup

# Ask a question answered by the docs
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "How long do refunds take?"}'
# -> 200, answer cites refund_policy.md#refund-timeline

# Ask another grounded question
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Can I change my email address?"}'
# -> 200, answer cites account_help.md#change-email-address

# Ask an out-of-scope question
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Which restaurants are nearby?"}'
# -> 200, answer should say it cannot confirm from the knowledge base
```

## Suggested Tech Stack

Python + FastAPI is recommended, but Challenge Track students may use any language or framework.

## Stretch Goals

Pick one or more after the core `/index` and `/chat` flow works.

### Score Threshold and Fallback

Add a retrieval score threshold. If the best sections or chunks are too weak, return an honest cannot-confirm answer instead of forcing a citation.

### Streaming Interface

After `/chat` works, add:

```text
POST /chat/stream
```

Use SSE to stream the answer token by token. A good streaming response should:

- Return selected sources first, so users can see what context the bot is using
- Stream answer tokens as they arrive
- End with a clear `done` event
- Preserve the same grounding and citation rules as `/chat`

Optional UI challenge: build a tiny HTML page that calls `/chat/stream` and renders the answer incrementally.

### Browser UI

Build a tiny browser UI over `/chat` or `/chat/stream`. Show selected sources before the answer so users can inspect grounding.

### Multi-Format Import

Add a small normalization pipeline before indexing:

```text
raw/*.txt or raw/*.html -> docs/*.md -> POST /index -> retrieval index
```

Requirements:

- Keep Markdown as the canonical knowledge format
- Preserve the original source filename
- Convert headings into Markdown headings
- Rebuild the retrieval index after import

Start with `.txt` or `.html`. More complex formats such as PDFs, spreadsheets, and transcripts can be discussed as production extensions.

### Alternative Interfaces

Expose the same retrieval core through another interface:

```text
CLI: kb index / kb ask
MCP: expose index, search, and chat as agent tools
Web UI: simple chat screen over /chat or /chat/stream
```

The goal is to compare interface tradeoffs, not to change the retrieval design.

### Wiki Index Generation

Generate `wiki/index.md` from `.kb/index.json` so humans and agents can browse the available topics.

### Answer Filing

Write useful Q&A results back into `wiki/` after review. Preserve citations back to the source Markdown sections.

### Conversation Memory

Add short conversation memory for follow-up questions. Memory can help interpret the query, but retrieved sources must still control the final answer.

### Paraphrase Comparison

Create paraphrased queries and compare Markdown KB vs Vector RAG. Look for synonym misses, semantic false positives, and citation quality.
