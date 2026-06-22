import json
import os

from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from . import indexer


CANNOT_CONFIRM = "I cannot confirm from the knowledge base."

SYSTEM_PROMPT = f"""You are a knowledge base Q&A assistant.
Rules:
1. Only answer using the provided CONTEXT.
2. Cite sources using filename#heading.
3. If the CONTEXT does not contain the answer, say: "{CANNOT_CONFIRM}"
4. Do not guess, invent policies, or use outside knowledge.
"""

# Q5 (weak/irrelevant retrieval -> honest fallback). BM25 scores are not
# normalized across queries, so we apply two complementary gates:
#   - MIN_SCORE: an absolute floor that drops near-zero keyword noise.
#   - REL_RATIO: a relative cutoff that drops secondary sections scoring far
#     below the top hit (filters semantic false positives without discarding a
#     legitimate single answer).
# RECALL_K widens recall before trimming; PROMPT_K caps how many sections reach
# the prompt (token-budget control).
MIN_SCORE = float(os.getenv("KB_MIN_SCORE", "0.5"))
REL_RATIO = float(os.getenv("KB_REL_RATIO", "0.3"))
RECALL_K = int(os.getenv("KB_RECALL_K", "5"))
PROMPT_K = int(os.getenv("KB_PROMPT_K", "3"))


def select_sections(question: str) -> list:
    """Retrieve, apply the threshold gates, and cap to the prompt budget."""
    ranked = indexer.search(question, k=RECALL_K, min_score=MIN_SCORE)
    if not ranked:
        return []
    top_score = ranked[0][1]
    kept = [(s, sc) for s, sc in ranked if sc >= top_score * REL_RATIO]
    return kept[:PROMPT_K]

_llm = None


def get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            request_timeout=20,
            max_retries=1,
        )
    return _llm


def build_prompt(query: str, ranked_sections: list) -> str:
    context_blocks = []
    for section, score in ranked_sections:
        heading_lines = "\n".join(
            f"{'#' * (idx + 1)} {heading}"
            for idx, heading in enumerate(section.heading_path)
        )
        context_blocks.append(
            f"[Source: {section.id}]\n"
            f"[BM25 score: {score:.2f}]\n"
            f"{heading_lines}\n\n"
            f"{section.content}"
        )

    context = "\n\n---\n\n".join(context_blocks)
    return f"CONTEXT:\n{context}\n\nQUESTION:\n{query}"


def format_sources(ranked_sections: list) -> list:
    return [
        {
            "source": section.id,
            "heading": " > ".join(section.heading_path),
            "score": round(score, 3),
            "content": section.content[:240],
        }
        for section, score in ranked_sections
    ]


NOT_INDEXED = "The knowledge base has not been indexed yet. Call POST /index first."


def query(question: str) -> dict:
    if not indexer.sections:
        return {"answer": NOT_INDEXED, "sources": []}

    ranked_sections = select_sections(question)
    if not ranked_sections:
        return {"answer": CANNOT_CONFIRM, "sources": []}

    response = get_llm().invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_prompt(question, ranked_sections)),
    ])

    return {
        "answer": response.content,
        "sources": format_sources(ranked_sections),
    }


def _sse(event: str, data: dict) -> str:
    """Serialize one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_query(question: str):
    """Yield SSE frames: sources first, then answer tokens, then a done event.

    Same grounding and citation rules as query(): sources are sent up front so
    the UI can show what context the answer is based on, and weak/empty
    retrieval streams the honest cannot-confirm message instead of an answer.
    """
    if not indexer.sections:
        yield _sse("sources", {"sources": []})
        yield _sse("token", {"text": NOT_INDEXED})
        yield _sse("done", {})
        return

    ranked_sections = select_sections(question)
    # Send selected sources before any token so the client can render grounding.
    yield _sse("sources", {"sources": format_sources(ranked_sections)})

    if not ranked_sections:
        yield _sse("token", {"text": CANNOT_CONFIRM})
        yield _sse("done", {})
        return

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_prompt(question, ranked_sections)),
    ]
    for chunk in get_llm().stream(messages):
        if chunk.content:
            yield _sse("token", {"text": chunk.content})
    yield _sse("done", {})
