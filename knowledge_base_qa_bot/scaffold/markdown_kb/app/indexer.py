import math
import re
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path


DOCS_DIR = Path(__file__).resolve().parents[3] / "docs"
INDEX_PATH = Path(__file__).resolve().parents[3] / ".kb" / "index.json"
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "is",
    "it",
    "my",
    "of",
    "the",
    "to",
    "what",
    "when",
    "which",
}


@dataclass
class Section:
    id: str
    file: str
    heading: str
    heading_path: list[str]
    content: str
    tokens: list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file": self.file,
            "heading": self.heading,
            "heading_path": self.heading_path,
            "content": self.content,
            "tokens": self.tokens,
        }


sections: list[Section] = []
doc_freq: Counter[str] = Counter()
avg_doc_len = 0.0
files_indexed = 0


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOP_WORDS]


def parse_markdown(path: Path) -> list[Section]:
    text = path.read_text(encoding="utf-8")
    filename = path.name
    result: list[Section] = []
    heading_stack: list[tuple[int, str]] = []
    current_heading: str | None = None
    content_lines: list[str] = []

    def flush():
        nonlocal current_heading, content_lines
        if current_heading is None:
            return
        content = "\n".join(content_lines).strip()
        heading_path = [h for _, h in heading_stack]
        result.append(Section(
            id=f"{filename}#{slugify(current_heading)}",
            file=filename,
            heading=current_heading,
            heading_path=heading_path,
            content=content,
            tokens=tokenize(current_heading + " " + content),
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
    return result


def write_index_json(index_path: Path = INDEX_PATH) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sections": [s.to_dict() for s in sections],
        "stats": {
            "files_indexed": files_indexed,
            "sections_indexed": len(sections),
            "avg_doc_len": avg_doc_len,
        },
    }
    index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def rebuild_stats() -> None:
    global doc_freq, avg_doc_len, files_indexed
    doc_freq.clear()
    for section in sections:
        for token in set(section.tokens):
            doc_freq[token] += 1
    avg_doc_len = sum(len(s.tokens) for s in sections) / len(sections) if sections else 0.0
    files_indexed = len({s.file for s in sections})


def load_index_json(index_path: Path = INDEX_PATH) -> tuple[int, int]:
    global sections
    if not index_path.exists():
        return 0, 0
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    sections = [
        Section(
            id=item["id"],
            file=item["file"],
            heading=item["heading"],
            heading_path=item["heading_path"],
            content=item["content"],
            tokens=item["tokens"],
        )
        for item in payload["sections"]
    ]
    rebuild_stats()
    return files_indexed, len(sections)


def build_index(docs_dir: Path = DOCS_DIR) -> tuple[int, int]:
    global sections, doc_freq, avg_doc_len, files_indexed

    sections = []
    doc_freq = Counter()
    avg_doc_len = 0.0
    files_indexed = 0

    for md_path in sorted(docs_dir.glob("*.md")):
        sections.extend(parse_markdown(md_path))

    rebuild_stats()
    write_index_json()
    return files_indexed, len(sections)


def bm25_score(query_tokens: list[str], section: Section, k1: float = 1.5, b: float = 0.75) -> float:
    if not query_tokens or not sections or avg_doc_len == 0.0:
        return 0.0
    tf = Counter(section.tokens)
    doc_len = len(section.tokens)
    n = len(sections)
    heading_tokens = set(tokenize(" ".join(section.heading_path)))
    score = 0.0
    for token in query_tokens:
        if token not in tf:
            continue
        f = tf[token]
        df = doc_freq.get(token, 0)
        if df == 0:
            continue
        idf = math.log((n - df + 0.5) / (df + 0.5) + 1)
        tf_norm = (f * (k1 + 1)) / (f + k1 * (1 - b + b * doc_len / avg_doc_len))
        boost = 1.5 if token in heading_tokens else 1.0
        score += idf * tf_norm * boost
    return score


def search(query: str, k: int = 3, min_score: float = 0.0) -> list[tuple[Section, float]]:
    query_tokens = tokenize(query)
    ranked = [
        (section, bm25_score(query_tokens, section))
        for section in sections
    ]
    ranked = [(section, score) for section, score in ranked if score > min_score]
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:k]
