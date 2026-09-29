import base64
import json
import os
import urllib.error
import urllib.request

import boto3

GATE_URL = os.environ["GATE_URL"].rstrip("/")
GATE_MODEL = os.environ["GATE_MODEL"]
KEY_PARAM = os.environ["KEY_PARAM"]

MAX_MESSAGE_CHARS = 500
MAX_TURNS = 6
MAX_HISTORY_CHARS = 2500

with open(os.path.join(os.path.dirname(__file__), "facts.md"), encoding="utf-8") as f:
    FACTS = f.read()

FRIENDLY = {
    400: (400, "That message can't be processed. Please leave out personal details such as emails or phone numbers, and try again."),
    413: (413, "That message is too long. Please shorten it."),
    429: (429, "Lots of questions right now. Please try again in a minute."),
    402: (503, "The assistant has reached its monthly limit. Please connect with Pranav on LinkedIn."),
}

_key = None


def _gate_key():
    global _key
    if _key is None:
        ssm = boto3.client("ssm")
        _key = ssm.get_parameter(Name=KEY_PARAM, WithDecryption=True)["Parameter"]["Value"]
    return _key


def _reply(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _clean(raw):
    if not isinstance(raw, list) or not raw:
        return None, "Send at least one message."
    turns = []
    for m in raw[-MAX_TURNS:]:
        if not isinstance(m, dict):
            return None, "Each message must be an object."
        role, content = m.get("role"), m.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            return None, "Each message needs a role (user or assistant) and text."
        turns.append({"role": role, "content": content.strip()})
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    if not turns or turns[-1]["role"] != "user":
        return None, "The last message must be the visitor's question."
    for a, b in zip(turns, turns[1:]):
        if a["role"] == b["role"]:
            return None, "Messages must alternate between user and assistant."
    if len(turns[-1]["content"]) > MAX_MESSAGE_CHARS:
        return None, f"Please keep questions under {MAX_MESSAGE_CHARS} characters."
    if sum(len(t["content"]) for t in turns) > MAX_HISTORY_CHARS:
        return None, "This conversation is getting long. Please start a new one."
    return turns, None


def handler(event, context):
    if event.get("requestContext", {}).get("http", {}).get("method") != "POST":
        return _reply(405, {"error": "Use POST."})

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", "replace")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return _reply(400, {"error": "Send JSON with a messages list."})

    turns, problem = _clean(data.get("messages") if isinstance(data, dict) else None)
    if problem:
        return _reply(400, {"error": problem})

    payload = {
        "model": GATE_MODEL,
        "system": FACTS,
        "messages": turns,
        "max_tokens": 300,
        "temperature": 0,
    }
    request = urllib.request.Request(
        f"{GATE_URL}/v1/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {_gate_key()}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read())
        answer = data["content"].strip()
        if data.get("stop_reason") == "max_tokens":
            answer += " …"
        return _reply(200, {"reply": answer})
    except urllib.error.HTTPError as error:
        request_id = error.headers.get("X-Request-ID", "unknown")
        print(json.dumps({"gateway_status": error.code, "request_id": request_id}))
        status, message = FRIENDLY.get(
            error.code, (502, "The assistant is unavailable right now. Please try again later.")
        )
        return _reply(status, {"error": message})
    except (urllib.error.URLError, TimeoutError):
        return _reply(504, {"error": "The assistant is taking too long. Please try again."})
