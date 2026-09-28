from fastapi import HTTPException
from redis.exceptions import RedisError

from app.redis_conn import client
from app.schemas import ChatRequest, ChatResponse

RUN_TTL_S = 3600


def uses_tools(req: ChatRequest) -> bool:
    return bool(req.tools) or any(m.role == "tool" or m.tool_calls for m in req.messages)


def check_tools(tenant, req: ChatRequest, actions: list[str]):
    if not uses_tools(req):
        return

    if tenant.agent_id is None:
        actions.append("blocked:tools_without_agent")
        raise HTTPException(403, "Tool use requires an agent identity. Use an agent key.")

    allowed = set((tenant.agent_policy or {}).get("allowed_tools", []))
    denied = sorted({t.name for t in req.tools} - allowed)
    if denied:
        actions.append("blocked:tool_not_allowed")
        raise HTTPException(
            403, f"Tools not allowed for agent '{tenant.agent_name}': {', '.join(denied)}"
        )


async def start_step(tenant, run_id: str | None, actions: list[str]):
    if tenant.agent_id is None:
        return
    if not run_id:
        raise HTTPException(400, "Agent requests must send an X-Agent-Run-ID header")

    policy = tenant.agent_policy or {}
    base = f"run:{tenant.agent_id}:{run_id}"

    try:
        steps = await client.incr(f"{base}:steps")
        await client.expire(f"{base}:steps", RUN_TTL_S)
        spent = float(await client.get(f"{base}:cost") or 0)
    except RedisError:
        raise HTTPException(503, "Agent run guard unavailable (fail-closed)")

    max_steps = policy.get("max_steps_per_run")
    if max_steps and steps > max_steps:
        actions.append("blocked:max_steps")
        raise HTTPException(403, f"Run '{run_id}' exceeded its limit of {max_steps} steps")

    max_cost = policy.get("max_cost_per_run_usd")
    if max_cost and spent >= max_cost:
        actions.append("blocked:run_budget")
        raise HTTPException(402, f"Run '{run_id}' reached its budget of ${max_cost}")

    actions.append(f"agent_step:{steps}")


async def add_run_cost(tenant, run_id: str | None, cost):
    if tenant.agent_id is None or not run_id or cost is None:
        return
    base = f"run:{tenant.agent_id}:{run_id}"
    try:
        await client.incrbyfloat(f"{base}:cost", float(cost))
        await client.expire(f"{base}:cost", RUN_TTL_S)
    except RedisError:
        pass


def review_tool_calls(tenant, req: ChatRequest, resp: ChatResponse, actions: list[str]):
    declared = {t.name for t in req.tools}
    needs_approval = set((tenant.agent_policy or {}).get("approval_required_tools", []))

    kept = []
    for call in resp.tool_calls:
        if call.name not in declared:
            actions.append(f"dropped:undeclared_tool:{call.name}")
            continue
        if call.name in needs_approval:
            call.requires_approval = True
            actions.append(f"approval_required:{call.name}")
        kept.append(call)
    resp.tool_calls = kept
