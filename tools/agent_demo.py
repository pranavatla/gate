import json
import os
import sys
import uuid

import httpx

GATEWAY = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8000") + "/v1/chat"
KEY = os.environ["AGENT_KEY"]
QUESTION = sys.argv[1]
MODEL = sys.argv[2] if len(sys.argv) > 2 else "anthropic/claude-haiku-4-5-20251001"

VERSES = {
    (2, 47): "You have a right to perform your prescribed duties, but you are not "
             "entitled to the fruits of your actions.",
    (2, 48): "Perform your duty equipoised, abandoning all attachment to success or failure.",
}

TOOLS = [
    {
        "name": "get_verse",
        "description": "Fetch the text of a Bhagavad Gita verse by chapter and verse number.",
        "parameters": {
            "type": "object",
            "properties": {"chapter": {"type": "integer"}, "verse": {"type": "integer"}},
            "required": ["chapter", "verse"],
        },
    },
    {
        "name": "save_reflection",
        "description": "Save a short reflection to the user's personal journal.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
]


def run_tool(call: dict) -> str:
    args = call["arguments"]
    if call["name"] == "get_verse":
        return VERSES.get((args.get("chapter"), args.get("verse")), "Verse not in demo data.")
    if call["name"] == "save_reflection":
        return "Reflection saved."
    return f"Unknown tool {call['name']}"


def main():
    run_id = uuid.uuid4().hex[:8]
    messages = [{"role": "user", "content": QUESTION}]
    print(f"run_id={run_id}  model={MODEL}\n")

    for step in range(1, 20):
        r = httpx.post(
            GATEWAY,
            timeout=60,
            headers={"Authorization": f"Bearer {KEY}", "X-Agent-Run-ID": run_id},
            json={"model": MODEL, "max_tokens": 400, "tools": TOOLS, "messages": messages},
        )
        print(f"step {step}: HTTP {r.status_code}  routed={r.headers.get('x-gate-routed-model')}"
              f"  policy={r.headers.get('x-gate-policy')}")

        if r.status_code != 200:
            print(f"  STOPPED BY GATEWAY: {r.json().get('detail')}")
            return

        data = r.json()
        if data["stop_reason"] != "tool_use":
            print(f"\nFINAL ANSWER (stop_reason={data['stop_reason']}):\n{data['content']}")
            return

        messages.append({"role": "assistant", "content": data["content"], "tool_calls": data["tool_calls"]})

        for call in data["tool_calls"]:
            print(f"  model wants: {call['name']}({json.dumps(call['arguments'])})")
            if call["requires_approval"]:
                answer = input(f"  APPROVAL NEEDED for {call['name']}. Allow? [y/N] ")
                result = run_tool(call) if answer.strip().lower() == "y" else "The user declined this action."
            else:
                result = run_tool(call)
            print(f"  tool result: {result}")
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})


if __name__ == "__main__":
    main()
