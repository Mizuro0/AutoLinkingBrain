from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import warnings

_SERVER_DIR = str(pathlib.Path(__file__).resolve().parents[1])
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)


def _patch_platform_for_py314_windows_ollama() -> None:
    """
    Work around Python 3.14 Windows platform WMI regression affecting ollama import.
    """
    if os.name != "nt":
        return
    try:
        import platform as _platform

        # ollama only needs these for User-Agent; stable fallbacks are enough.
        _platform.machine = lambda: os.environ.get("PROCESSOR_ARCHITECTURE", "unknown")
        _platform.system = lambda: "Windows"
    except Exception:
        pass


_patch_platform_for_py314_windows_ollama()

from mem0 import Memory

from autolinkingbrain.mem0_settings import mem0_vector_config


def _load_mem0() -> Memory:
    config = mem0_vector_config()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Memory.from_config(config_dict=config)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Migrate memories from aggregated project_<slug> to dedicated project channels."
    )
    p.add_argument("--source-slug", help="Source slug without 'project_' prefix.")
    p.add_argument(
        "--targets",
        nargs="+",
        help="Target slugs without 'project_' prefix (example: backend frontend api_gateway).",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=5000,
        help="How many rows to read from source channel.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print migration plan without writing to Mem0.",
    )
    p.add_argument(
        "--export-ambiguous",
        default="",
        help="Path to JSONL file for ambiguous rows (empty disables export).",
    )
    p.add_argument(
        "--list-channels",
        action="store_true",
        help="List project_* channels that have rows and exit.",
    )
    return p


def _list_channels(mem0: Memory, top_k: int = 5000) -> int:
    """Scan common slugs + anything seen in a small chroma peek."""
    from autolinkingbrain.mem0_settings import mem0_vector_config

    cfg = mem0_vector_config()
    collection = (cfg.get("vector_store") or {}).get("config") or {}
    collection_name = collection.get("collection_name", "mem0")

    slugs: set[str] = set()
    try:
        import chromadb

        path = collection.get("path", "")
        if path:
            client = chromadb.PersistentClient(path=path)
            coll = client.get_or_create_collection(collection_name)
            peek = coll.get(include=["metadatas"], limit=min(top_k, 10000))
            for meta in peek.get("metadatas") or []:
                if isinstance(meta, dict):
                    uid = str(meta.get("user_id") or "")
                    if uid.startswith("project_"):
                        slugs.add(uid[len("project_") :])
    except Exception:
        pass

    rows_by_channel: list[tuple[str, int]] = []
    for slug in sorted(slugs):
        uid = f"project_{slug}"
        raw = mem0.get_all(filters={"user_id": uid}, top_k=max(1, top_k))
        rows = raw.get("results", []) if isinstance(raw, dict) else (raw or [])
        count = len([r for r in rows if isinstance(r, dict) and (r.get("memory") or "").strip()])
        if count:
            rows_by_channel.append((uid, count))

    if not rows_by_channel:
        print("No project_* channels with rows found.")
        return 0
    print("Channels with data:")
    for uid, count in sorted(rows_by_channel, key=lambda x: (-x[1], x[0])):
        print(f"  {uid}: {count}")
    return 0


def _route_memory(text: str, targets: list[str]) -> list[str]:
    """Heuristic routing by explicit project token in text."""
    lowered = (text or "").lower()
    hits: list[str] = []
    for t in targets:
        escaped = re.escape(t.lower())
        if re.search(rf"(?<![a-z0-9_]){escaped}(?![a-z0-9_])", lowered):
            hits.append(t)
    return hits


def main() -> int:
    args = _build_arg_parser().parse_args()
    mem0 = _load_mem0()

    if args.list_channels:
        return _list_channels(mem0, top_k=args.top_k)

    if not args.source_slug or not args.targets:
        print("error: --source-slug and --targets are required unless --list-channels is set", file=sys.stderr)
        return 2

    source_user_id = f"project_{args.source_slug}"
    raw = mem0.get_all(filters={"user_id": source_user_id}, top_k=max(1, args.top_k))
    rows = raw.get("results", []) if isinstance(raw, dict) else (raw or [])
    rows = [r for r in rows if isinstance(r, dict) and (r.get("memory") or "").strip()]

    planned: dict[str, int] = {t: 0 for t in args.targets}
    ambiguous = 0
    ambiguous_rows: list[dict] = []
    for row in rows:
        text = row.get("memory") or ""
        targets = _route_memory(text, args.targets)
        if len(targets) == 1:
            planned[targets[0]] += 1
        elif len(targets) > 1:
            ambiguous += 1
            ambiguous_rows.append(
                {
                    "id": row.get("id"),
                    "matched_targets": targets,
                    "memory": text,
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                    "source_user_id": source_user_id,
                }
            )

    print(f"Source: {source_user_id}")
    print(f"Rows scanned: {len(rows)}")
    for target, cnt in planned.items():
        print(f"Plan -> project_{target}: {cnt}")
    print(f"Ambiguous (matches >1 target): {ambiguous}")
    if not rows:
        print("Hint: run with --list-channels to see which project_* channels actually have data.")

    if args.dry_run:
        if args.export_ambiguous:
            out_path = pathlib.Path(args.export_ambiguous)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w", encoding="utf-8") as f:
                for item in ambiguous_rows:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            print(f"Ambiguous export: {out_path} ({len(ambiguous_rows)} rows)")
        print("Dry-run complete. No writes performed.")
        return 0

    written = 0
    for row in rows:
        text = row.get("memory") or ""
        targets = _route_memory(text, args.targets)
        if len(targets) != 1:
            continue
        target_user_id = f"project_{targets[0]}"
        # Skip LLM extraction: migration copies existing facts; avoids Ollama chat on every row.
        mem0.add(text, user_id=target_user_id, infer=False)
        written += 1

    print(f"Migration complete. Written rows: {written}")
    if args.export_ambiguous:
        out_path = pathlib.Path(args.export_ambiguous)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for item in ambiguous_rows:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"Ambiguous export: {out_path} ({len(ambiguous_rows)} rows)")
    print("Note: source rows were NOT deleted. Review and clean up manually if needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
