"""Lossless recovery of a corrupted ChromaDB HNSW index.

The SQLite store keeps document text + channel (user_id) intact even when the
vector index segment is corrupted (Rust _add access violation). This re-embeds the
recovered documents into a fresh vector store on the same path.

Phases:
  extract  — read-only: dump all graph_brain memories to a JSON file.
  rebuild  — back up chroma_data, drop only Chroma artifacts (keep .brain/.codegraph/
             .cursor), then re-insert every memory via mem0 (re-embeds through Ollama).

Usage:
  python scripts/_chroma_recover.py extract
  python scripts/_chroma_recover.py rebuild
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHROMA_DIR = Path(os.environ.get("MEM0_CHROMA_PATH", str(ROOT / "chroma_data")))
SQLITE = CHROMA_DIR / "chroma.sqlite3"
DUMP = ROOT / "scripts" / "_recovered_memories.json"
COLLECTION = os.environ.get("MEM0_COLLECTION", "graph_brain")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _metadata_segment(cur: sqlite3.Cursor, collection: str) -> str:
    """Find the sqlite/metadata segment id for a collection (data source of truth)."""
    row = cur.execute("select id from collections where name=?", (collection,)).fetchone()
    if not row:
        raise SystemExit(f"collection {collection!r} not found in {SQLITE}")
    coll_id = row[0]
    seg = cur.execute(
        "select id from segments where collection=? and scope='METADATA'", (coll_id,)
    ).fetchone()
    if not seg:
        raise SystemExit(f"no METADATA segment for collection {collection!r}")
    return seg[0]


def _meta_value(key: str, sv, iv, fv, bv):
    if sv is not None:
        return sv
    if iv is not None:
        return iv
    if fv is not None:
        return fv
    if bv is not None:
        return bool(bv)
    return None


def extract() -> list[dict]:
    con = sqlite3.connect(str(SQLITE))
    cur = con.cursor()
    segment = _metadata_segment(cur, COLLECTION)
    emb_ids = [r[0] for r in cur.execute(
        "select id from embeddings where segment_id=?", (segment,)
    ).fetchall()]
    memories: list[dict] = []
    for eid in emb_ids:
        meta: dict = {}
        for key, sv, iv, fv, bv in cur.execute(
            "select key, string_value, int_value, float_value, bool_value "
            "from embedding_metadata where id=?", (eid,)
        ).fetchall():
            meta[key] = _meta_value(key, sv, iv, fv, bv)
        text = meta.get("data")
        user_id = meta.get("user_id")
        if not text or not user_id:
            continue
        memories.append({
            "text": text,
            "user_id": user_id,
            "role": meta.get("role"),
            "attributed_to": meta.get("attributed_to"),
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
        })
    con.close()
    return memories


def cmd_extract() -> int:
    mems = extract()
    DUMP.write_text(json.dumps(mems, ensure_ascii=False, indent=2), encoding="utf-8")
    by_chan: dict[str, int] = {}
    for m in mems:
        by_chan[m["user_id"]] = by_chan.get(m["user_id"], 0) + 1
    print(f"extracted {len(mems)} memories -> {DUMP}")
    for chan, n in sorted(by_chan.items(), key=lambda x: -x[1]):
        print(f"  {chan}: {n}")
    return 0


def _backup() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dst = CHROMA_DIR.parent / f"chroma_data.bak_{ts}"
    shutil.copytree(CHROMA_DIR, dst)
    return dst


def _wipe_chroma_artifacts() -> list[str]:
    removed: list[str] = []
    for name in ("chroma.sqlite3", "chroma.sqlite3-wal", "chroma.sqlite3-shm"):
        p = CHROMA_DIR / name
        if p.exists():
            p.unlink()
            removed.append(name)
    for child in CHROMA_DIR.iterdir():
        if child.is_dir() and _UUID_RE.match(child.name):
            shutil.rmtree(child)
            removed.append(child.name + "/")
    return removed


def cmd_rebuild() -> int:
    if not DUMP.is_file():
        print("run 'extract' first (no dump found)", file=sys.stderr)
        return 1
    mems = json.loads(DUMP.read_text(encoding="utf-8"))
    print(f"loaded {len(mems)} memories from dump")

    backup = _backup()
    print(f"backup -> {backup}")
    removed = _wipe_chroma_artifacts()
    print(f"removed chroma artifacts: {removed}")

    os.environ.setdefault("MEM0_TELEMETRY", "false")
    from mem0 import Memory

    from autolinkingbrain.mem0_settings import mem0_vector_config

    db = Memory.from_config(config_dict=mem0_vector_config())
    print("fresh Memory ready; re-inserting…")

    ok = 0
    fail = 0
    t0 = time.monotonic()
    for i, m in enumerate(mems, 1):
        meta = {}
        if m.get("role"):
            meta["role"] = m["role"]
        if m.get("attributed_to"):
            meta["attributed_to"] = m["attributed_to"]
        try:
            kwargs = {"user_id": m["user_id"], "infer": False}
            if meta:
                kwargs["metadata"] = meta
            db.add(m["text"], **kwargs)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"  [{i}] FAIL {type(exc).__name__}: {exc}")
        if i % 50 == 0:
            print(f"  {i}/{len(mems)} ({time.monotonic()-t0:.0f}s)")
    print(f"done: ok={ok} fail={fail} in {time.monotonic()-t0:.0f}s")
    return 0 if fail == 0 else 2


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else "extract"
    if phase == "extract":
        return cmd_extract()
    if phase == "rebuild":
        return cmd_rebuild()
    print(f"unknown phase: {phase} (use extract|rebuild)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
