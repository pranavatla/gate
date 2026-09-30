import io
import json
import re
import zipfile

import yaml
from fastapi import APIRouter, Depends, Header, HTTPException, Request

router = APIRouter(prefix="/v1/okf", tags=["OKF"])
MAX_BUNDLE_BYTES = 1 * 1024 * 1024
MAX_EXPANDED_BYTES = 1 * 1024 * 1024
MAX_FILES = 500
MAX_CONCEPT_CHARS = 100_000
MAX_CONTEXT_CHARS = 4_000
_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)(.*)\Z", re.S)


async def _tenant(authorization: str | None = Header(default=None)):
    from app.auth import get_tenant

    return await get_tenant(authorization)


def parse_bundle(raw: bytes) -> dict[str, str]:
    if len(raw) > MAX_BUNDLE_BYTES:
        raise HTTPException(413, "OKF bundle exceeds 1 MB")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        files = [item for item in archive.infolist() if not item.is_dir()]
        if not files or len(files) > MAX_FILES:
            raise ValueError("bundle must contain 1 to 500 files")
        if sum(item.file_size for item in files) > MAX_EXPANDED_BYTES:
            raise ValueError("expanded bundle exceeds 1 MB")
        docs = {}
        seen_paths = set()
        for item in files:
            path = item.filename.replace("\\", "/")
            parts = path.split("/")
            if path.startswith("/") or any(part in ("", ".", "..") for part in parts):
                raise ValueError("invalid path")
            if path in seen_paths:
                raise ValueError(f"duplicate path: {path}")
            seen_paths.add(path)
            if item.file_size > MAX_CONCEPT_CHARS:
                raise ValueError("file exceeds 100 KB")
            if parts[-1].endswith(".md") and parts[-1] not in ("index.md", "log.md"):
                text = archive.read(item).decode("utf-8")
                match = _FRONTMATTER.fullmatch(text)
                if not match:
                    raise ValueError(f"{path}: missing YAML frontmatter")
                metadata = yaml.safe_load(match.group(1))
                if not isinstance(metadata, dict) or not isinstance(metadata.get("type"), str) or not metadata["type"].strip():
                    raise ValueError(f"{path}: frontmatter needs a non-empty type")
                docs[path[:-3]] = f"{path}\n{match.group(2).strip()}"
        if not docs:
            raise ValueError("bundle contains no concept documents")
        return docs
    except (zipfile.BadZipFile, UnicodeDecodeError, yaml.YAMLError, ValueError, RuntimeError) as exc:
        raise HTTPException(400, f"Invalid OKF bundle: {exc}") from exc


@router.post("/{bundle_id}")
async def upload_bundle(
    bundle_id: str,
    request: Request,
    tenant=Depends(_tenant),
):
    from app import db
    from app.ratelimit import check_before_call

    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", bundle_id):
        raise HTTPException(400, "Bundle ID must be 1-64 letters, numbers, underscores or hyphens")
    if tenant.agent_id is not None:
        raise HTTPException(403, "Agent keys cannot manage OKF bundles")
    await check_before_call(tenant)
    raw = await request.body()
    documents = parse_bundle(raw)
    await db.pool.execute(
        """INSERT INTO okf_bundles (tenant_id, bundle_id, documents)
           VALUES ($1, $2, $3::jsonb)
           ON CONFLICT (tenant_id, bundle_id) DO UPDATE SET documents = EXCLUDED.documents,
             created_at = now()""",
        tenant.id, bundle_id, documents,
    )
    return {"bundle_id": bundle_id, "concepts": len(documents)}


async def get_context(tenant_id: int, bundle_id: str, concept_ids: list[str]) -> str:
    from app import db
    row = await db.pool.fetchrow(
        "SELECT documents FROM okf_bundles WHERE tenant_id = $1 AND bundle_id = $2",
        tenant_id, bundle_id,
    )
    if row is None:
        raise HTTPException(404, "OKF bundle not found")
    docs = row["documents"]
    if concept_ids:
        missing = set(concept_ids) - docs.keys()
        if missing:
            raise HTTPException(404, f"OKF concepts not found: {', '.join(sorted(missing))}")
        selected = concept_ids
    else:
        selected = sorted(docs)
    context = bundle_id + ":" + json.dumps(selected) + "\n\n" + "\n\n---\n\n".join(
        docs[key] for key in selected
    )
    if len(context) > MAX_CONTEXT_CHARS:
        raise HTTPException(413, "OKF context too large; choose fewer concepts")
    return context


if __name__ == "__main__":
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("index.md", "# Knowledge")
        archive.writestr("guide/start.md", "---\ntype: Playbook\n---\n# Start")
    assert parse_bundle(buffer.getvalue()) == {"guide/start": "guide/start.md\n# Start"}
