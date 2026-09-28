import hashlib
import secrets

TENANT_PREFIX = "gk_"
AGENT_PREFIX = "ga_"


def generate_key(prefix: str = TENANT_PREFIX) -> str:
    return prefix + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def display_prefix(key: str) -> str:
    return key[:10]