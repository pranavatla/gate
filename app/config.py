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
DATABASE_URL = require("DATABASE_URL")
REDIS_URL= require("REDIS_URL")
CHAOS_ENABLED = os.getenv("CHAOS_ENABLED", "false") == "true"
RATELIMIT_FAIL_OPEN = os.getenv("RATELIMIT_FAIL_OPEN", "true") == "true"
BEDROCK_API_KEY = os.getenv("BEDROCK_API_KEY", "")
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "ap-south-1")
GATE_CHATBOT_TENANT = os.getenv("GATE_CHATBOT_TENANT", "gate-chatbot")
GATE_CHATBOT_MODEL = os.getenv("GATE_CHATBOT_MODEL", "anthropic/claude-sonnet-4-5-20250929")