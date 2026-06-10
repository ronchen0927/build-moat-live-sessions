import os

from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from . import indexer


SYSTEM_PROMPT = """You are a knowledge base Q&A assistant.
Rules:
1. Only answer using the provided CONTEXT.
2. Cite sources using filename#heading.
3. If the CONTEXT does not contain the answer, say: "I cannot confirm from the knowledge base."
4. Do not guess, invent policies, or use outside knowledge.
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
    context_blocks = []
    for doc, score in ranked_chunks:
        context_blocks.append(
            f"[Source: {doc.metadata.get('source', 'unknown')}]\n"
            f"[Vector distance: {score:.4f}]\n"
            f"{doc.page_content}"
        )
    context = "\n\n---\n\n".join(context_blocks)
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
