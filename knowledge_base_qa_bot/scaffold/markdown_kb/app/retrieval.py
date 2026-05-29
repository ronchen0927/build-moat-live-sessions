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


def build_prompt(query: str, ranked_sections: list) -> str:
    parts = []
    for section, _score in ranked_sections:
        heading_path_str = " > ".join(section.heading_path)
        parts.append(
            f"[Source: {section.id}]\n"
            f"Heading: {heading_path_str}\n\n"
            f"{section.content}"
        )
    context = "\n\n---\n\n".join(parts)
    return f"CONTEXT:\n{context}\n\nQUESTION:\n{query}"


def query(question: str) -> dict:
    if not indexer.sections:
        return {
            "answer": "The knowledge base has not been indexed yet. Call POST /index first.",
            "sources": [],
        }

    ranked_sections = indexer.search(question, k=3)
    if not ranked_sections:
        return {
            "answer": "I cannot confirm from the knowledge base.",
            "sources": [],
        }

    response = get_llm().invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_prompt(question, ranked_sections)),
    ])

    sources = [
        {
            "source": section.id,
            "heading": " > ".join(section.heading_path),
            "score": round(score, 3),
            "content": section.content[:240],
        }
        for section, score in ranked_sections
    ]

    return {
        "answer": response.content,
        "sources": sources,
    }
