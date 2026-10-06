"""Metadata-only LangSmith instrumentation; enabled with LANGSMITH_TRACING."""
import os
import json
from langsmith import traceable, get_current_run_tree
from langsmith import Client

_client = Client()


def _serialize_value(v):
    """Serialize values for LangSmith: handle Pydantic models, responses, and basic types."""
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, dict):
        return {k: _serialize_value(v) for k, v in v.items()}
    if isinstance(v, (list, tuple)):
        return [_serialize_value(i) for i in v]
    # Pydantic model or other object with dict() or model_dump()
    if hasattr(v, "model_dump"):
        return _serialize_value(v.model_dump())
    if hasattr(v, "dict"):
        return _serialize_value(v.dict())
    # FastAPI Response objects
    if hasattr(v, "body"):
        try:
            return json.loads(v.body) if isinstance(v.body, bytes) else v.body
        except Exception:
            return str(v)
    return str(v)


def traced(name, run_type="chain"):
    def process_inputs(inputs):
        if isinstance(inputs, dict):
            return {k: _serialize_value(v) for k, v in inputs.items()}
        if isinstance(inputs, (list, tuple)):
            return [_serialize_value(v) for v in inputs]
        return _serialize_value(inputs)

    def process_outputs(outputs):
        return _serialize_value(outputs)

    return traceable(name=name, run_type=run_type, client=_client,
                     process_inputs=process_inputs, process_outputs=process_outputs)


def annotate(**metadata):
    run = get_current_run_tree()
    if run is not None:
        run.add_metadata(metadata)


def usage(model, input_tokens, output_tokens=0, input_cost=None, output_cost=None):
    run = get_current_run_tree()
    if run is None:
        return
    provider, _, model_name = model.partition("/")
    values = {"input_tokens": input_tokens, "output_tokens": output_tokens,
              "total_tokens": input_tokens + output_tokens}
    if input_cost is not None and output_cost is not None:
        values.update(input_cost=float(input_cost), output_cost=float(output_cost),
                      total_cost=float(input_cost + output_cost))
    run.add_metadata({"ls_provider": provider, "ls_model_name": model_name,
                      "cost_owner": True, "cost_source": "calculated" if input_cost is not None else "langsmith_model_pricing"})
    run.set(usage_metadata=values)


def trace_headers():
    run = get_current_run_tree()
    # Send only the trace lineage; Gate supplies trusted tenant/application metadata.
    return {"langsmith-trace": run.to_headers()["langsmith-trace"]} if run else {}


def flush():
    if os.getenv("LANGSMITH_TRACING", "").lower() == "true":
        _client.flush(timeout=2)
