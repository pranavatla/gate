"""Per-provider view for GET /v1/stats: every provider the gateway can route to, even idle ones.

models_7d only lists models that served a successful call in the window, so a provider with no
recent traffic would vanish from obs.atla.in. This lists every wired provider with its catalog
models and its 7-day usage. Plain data in, plain data out: no database or config imports, so it
is unit-tested without a running gateway.
"""


def provider_summary(providers, catalog, models_7d):
    """providers: provider names in routing order (the router's ADAPTERS keys).
    catalog: (provider, model_id) pairs from the price table, the models the gateway will accept.
    models_7d: [{"model": "provider/model-id", "calls", "tokens", "cost_usd"}] from successful calls.
    """
    out = []
    for name in providers:
        used = [m for m in models_7d if m["model"].partition("/")[0] == name]
        out.append({
            "provider": name,
            "catalog_models": sorted(f"{name}/{model}" for p, model in catalog if p == name),
            "calls_7d": sum(int(m["calls"]) for m in used),
            "tokens_7d": sum(int(m["tokens"]) for m in used),
            "cost_usd_7d": round(sum(float(m["cost_usd"]) for m in used), 6),
        })
    return out
