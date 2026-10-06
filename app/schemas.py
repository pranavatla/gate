from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = {}
    requires_approval: bool = False


class Tool(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}


class Message(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    system: str | None = None
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float | None = Field(default=None, ge=0, le=1)
    tools: list[Tool] = []
    okf_bundle: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    okf_concepts: list[str] = Field(default=[], max_length=20)
    prompt: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    user_key: str | None = Field(default=None, max_length=128)


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class ChatResponse(BaseModel):
    provider: str
    model: str
    content: str
    usage: Usage
    stop_reason: str = "end"
    tool_calls: list[ToolCall] = []
