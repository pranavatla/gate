import re
from dataclasses import dataclass

from fastapi import HTTPException

from app.schemas import ChatRequest

PII_PATTERNS = {
    "email":   re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "card":    re.compile(r"\b(?:\d[ -]?){12,18}\d\b"),
    "aadhaar": re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b"),
    "phone":   re.compile(r"(?<!\d)(?:\+91[ -]?)?[6-9]\d{9}(?!\d)"),
    "pan":     re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
}


def _luhn_ok(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def scan_pii(text: str) -> tuple[str, list[str]]:
    found: list[str] = []
    for kind, pattern in PII_PATTERNS.items():
        def replace(match, kind=kind):
            if kind == "card" and not _luhn_ok(match.group()):
                return match.group()
            found.append(kind)
            return f"[{kind.upper()}]"
        text = pattern.sub(replace, text)
    return text, found


@dataclass
class PolicyResult:
    request: ChatRequest
    allowed_models: set[str] | None


def apply_policy(tenant, req: ChatRequest, actions: list[str]) -> PolicyResult:
    p = tenant.policy or {}

    allowed = set(p["allowed_models"]) if p.get("allowed_models") else None
    if allowed is not None and req.model not in allowed:
        actions.append("blocked:model_not_allowed")
        raise HTTPException(403, f"Model '{req.model}' is not allowed for this tenant")

    all_text = (req.system or "") + " ".join(m.content for m in req.messages)

    limit = p.get("max_input_chars")
    if limit and len(all_text) > limit:
        actions.append("blocked:input_too_long")
        raise HTTPException(413, f"Input too long: {len(all_text)} characters (limit {limit})")

    lowered = all_text.lower()
    for term in p.get("blocked_terms", []):
        if term.lower() in lowered:
            actions.append("blocked:content_term")
            raise HTTPException(400, "Request blocked by content policy")

    messages = req.messages
    system = req.system
    mode = p.get("pii_mode", "off")

    if mode != "off":
        found: list[str] = []
        cleaned = []
        for m in req.messages:
            text, kinds = scan_pii(m.content)
            found += kinds
            cleaned.append(m.model_copy(update={"content": text}))
        if system:
            system, kinds = scan_pii(system)
            found += kinds

        if found:
            kinds = ",".join(sorted(set(found)))
            if mode == "block":
                actions.append(f"blocked:pii({kinds})")
                raise HTTPException(400, f"Request contains personal data ({kinds}). Remove it and try again.")
            messages = cleaned
            actions.append(f"pii_redacted:{kinds}")

    max_tokens = req.max_tokens
    cap = p.get("max_tokens_cap")
    if cap and max_tokens > cap:
        actions.append(f"max_tokens_clamped:{max_tokens}->{cap}")
        max_tokens = cap

    enforced = p.get("system_prompt")
    if enforced:
        system = enforced + ("\n\n" + system if system else "")
        actions.append("system_prompt_enforced")

    new_req = req.model_copy(
        update={"messages": messages, "system": system, "max_tokens": max_tokens}
    )
    return PolicyResult(new_req, allowed)
