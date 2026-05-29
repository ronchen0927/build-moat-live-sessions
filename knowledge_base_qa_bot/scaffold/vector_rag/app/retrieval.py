import os

from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from . import indexer


SYSTEM_PROMPT = """You are a customer support assistant for a knowledge base Q&A system.

RULES:
1. Answer ONLY using information from the CONTEXT provided below.
2. Cite sources using the exact source IDs shown as [Source: ...] in the context. Source IDs use the format filename#heading-slug.
3. If the CONTEXT does not contain the answer, respond exactly: "I cannot confirm that from the knowledge base."
4. Never guess, infer beyond the context, or use outside knowledge.
5. Be concise and direct.
"""

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


def build_prompt(query: str, ranked_chunks: list) -> str:
    parts = []
    for doc, _score in ranked_chunks:
        source = doc.metadata.get("source", "unknown")
        heading = doc.metadata.get("heading", "unknown")
        parts.append(
            f"[Source: {source}]\n"
            f"Heading: {heading}\n\n"
            f"{doc.page_content}"
        )
    context = "\n\n---\n\n".join(parts)
    return f"CONTEXT:\n{context}\n\nQUESTION:\n{query}"


def query(question: str) -> dict:
    if indexer.vectorstore is None:
        return {
            "answer": "The knowledge base has not been indexed yet. Call POST /index first.",
            "sources": [],
        }

    ranked_chunks = indexer.search(question, k=3)
    if not ranked_chunks:
        return {
            "answer": "I cannot confirm from the knowledge base.",
            "sources": [],
        }

    response = get_llm().invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_prompt(question, ranked_chunks)),
    ])

    sources = [
        {
            "source": doc.metadata.get("source", "unknown"),
            "heading": doc.metadata.get("heading", "unknown"),
            "score": round(float(score), 3),
            "content": doc.page_content[:240],
        }
        for doc, score in ranked_chunks
    ]

    return {
        "answer": response.content,
        "sources": sources,
    }
