import hashlib
import secrets

PREFIX = "gk_"


def generate_key() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def display_prefix(key: str) -> str:
    return key[:10]
