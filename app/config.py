import os
from dotenv import load_dotenv

load_dotenv()


def require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is missing from .env")
    return value


ANTHROPIC_API_KEY = require("ANTHROPIC_API_KEY")
OPENAI_API_KEY = require("OPENAI_API_KEY")
GEMINI_API_KEY = require("GEMINI_API_KEY")
