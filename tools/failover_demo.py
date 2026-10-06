#!/usr/bin/env python3
"""Live failover demo: knock providers out one by one and watch the gateway route around them.

How it works: the gateway has a chaos switch. When the gateway runs with CHAOS_ENABLED=true, a Redis key
chaos:<provider> makes every call to that provider fail with a 503. This script sets those keys, sends
real requests through /v1/chat, and prints which model actually answered.

    GATEWAY_URL=http://127.0.0.1:8000 GATE_API_KEY=gk_... REDIS_URL=redis://127.0.0.1:6379/0 \\
        python tools/failover_demo.py [primary-model]

The chaos key affects EVERY request the gateway handles while it is set, including real visitors.
Run it against a local or staging stack, or against production only for a short, deliberate demo
(the script asks you to confirm for non-local gateways). It always clears the keys and the circuit
breaker state on exit, even on Ctrl-C.
"""
import os
import sys
import time
import uuid

import httpx
import redis

GATEWAY = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8000").rstrip("/")
KEY = os.environ["GATE_API_KEY"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
MODEL = sys.argv[1] if len(sys.argv) > 1 else "bedrock/global.amazon.nova-2-lite-v1:0"
PROVIDERS = ["bedrock", "gemini", "openai", "anthropic"]
CHAOS_TTL_S = 300

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def reset():
    """Remove injected failures and any circuit-breaker state they caused."""
    keys = []
    for p in PROVIDERS:
        keys += [f"chaos:{p}"] + [f"cb:{p}:{s}" for s in ("open", "fails", "tripped", "probe")]
    r.delete(*keys)


def ask(label: str):
    body = {
        "model": MODEL,
        "max_tokens": 40,
        "temperature": 0,
        # unique text each time so the semantic cache never answers instead of a provider
        "messages": [{"role": "user", "content": f"Reply with one short sentence about gateways. ({uuid.uuid4().hex[:8]})"}],
    }
    t0 = time.perf_counter()
    res = httpx.post(f"{GATEWAY}/v1/chat", json=body, headers={"Authorization": f"Bearer {KEY}"}, timeout=60)
    ms = int((time.perf_counter() - t0) * 1000)
    if res.status_code == 200:
        h = res.headers
        routed = h.get("X-Gate-Routed-Model", "?")
        tag = "FAILED OVER" if h.get("X-Gate-Fallback") == "true" else "primary"
        print(f"  {label:<34} 200  {routed:<42} {tag:<12} {ms} ms")
    else:
        detail = res.json().get("detail", res.text) if res.headers.get("content-type", "").startswith("application/json") else res.text
        print(f"  {label:<34} {res.status_code}  {str(detail)[:70]}  {ms} ms")


def knock_out(*providers: str):
    for p in providers:
        r.set(f"chaos:{p}", 1, ex=CHAOS_TTL_S)
    print(f"\n>> injected failures: {', '.join(providers)}")


def main():
    if not GATEWAY.startswith(("http://127.0.0.1", "http://localhost")):
        print(f"Target is {GATEWAY}. Injected failures hit all live traffic on it while they are set.")
        if input("Type YES to continue: ") != "YES":
            sys.exit("aborted")

    print(f"Gateway {GATEWAY}, primary model {MODEL}\n")
    print("  step                               code routed model                              result       latency")
    try:
        reset()
        ask("1. everything healthy")

        knock_out("bedrock")
        ask("2. bedrock down")
        ask("   bedrock still down (breaker open)")

        knock_out("gemini")
        ask("3. bedrock + gemini down")

        knock_out("openai", "anthropic")
        ask("4. every provider down")

        reset()
        print("\n>> failures cleared")
        ask("5. recovered")
    finally:
        reset()
        print("\nchaos keys and circuit-breaker state cleared.")


if __name__ == "__main__":
    main()
