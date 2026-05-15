import hashlib
import string
import time

from sqlalchemy.orm import Session

from .models import UrlMapping

BASE62_CHARS = string.ascii_letters + string.digits
TOKEN_LENGTH = 7
MAX_RETRIES = 10


def base62_encode(data: bytes) -> str:
    num = int.from_bytes(data, "big")
    if num == 0:
        return BASE62_CHARS[0]
    result = []
    while num > 0:
        num, remainder = divmod(num, 62)
        result.append(BASE62_CHARS[remainder])
    return "".join(reversed(result))


def _token_exists(db: Session, token: str) -> bool:
    return db.query(UrlMapping).filter(UrlMapping.token == token).first() is not None


def generate_token(url: str, db: Session) -> str:
    """SHA-256(url + nonce) → base62 → 7 chars, retry on collision."""
    for attempt in range(MAX_RETRIES):
        nonce = f"{url}{attempt}{time.time_ns()}"
        digest = hashlib.sha256(nonce.encode()).digest()
        token = base62_encode(digest)[:TOKEN_LENGTH]
        if not _token_exists(db, token):
            return token
    raise RuntimeError("Failed to generate a unique token after max retries")
