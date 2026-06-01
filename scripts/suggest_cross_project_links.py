#!/usr/bin/env python3
"""
Строит предложения межпроектных связей между фактами Mem0 через Ollama.

Читает все записи (как viewer), отправляет модели компактные выдержки попарно
по каналам (`project_*`, а также `global_skills` / `global_topology` ↔ проект),
получает JSON-массив рёбер и дописывает в memory_cross_links.json (дедупликация).

Переменные окружения:
  OLLAMA_HOST       — по умолчанию http://127.0.0.1:11434
  OLLAMA_LLM        — имя модели (как в mem0_settings / ollama)
  MEM0_TELEMETRY=0 — отключить телеметрию mem0 при обходе (рекомендуется)

Примеры:
  .venv\\Scripts\\python scripts\\suggest_cross_project_links.py --dry-run
  .venv\\Scripts\\python scripts\\suggest_cross_project_links.py --apply --max-pairs 8 --sync-mem0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_SERVER_DIR = str(Path(__file__).resolve().parents[1])
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

os.environ.setdefault("MEM0_TELEMETRY", "false")

from autolinkingbrain.brain_link_store import merge_edges, save_cross_links  # noqa: E402
from viewer_server import _fetch_all  # noqa: E402


def _ollama_generate(host: str, model: str, prompt: str, timeout_s: float = 600.0) -> str:
    url = f"{host.rstrip('/')}/api/generate"
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.load(resp)
    return str(data.get("response") or "")


def _extract_json_array(text: str) -> list:
    t = text.strip()
    i0 = t.find("[")
    i1 = t.rfind("]")
    if i0 < 0 or i1 <= i0:
        raise ValueError("В ответе модели нет JSON-массива [...]")
    return json.loads(t[i0 : i1 + 1])


def _compact_nodes(payload: dict) -> list[dict]:
    out: list[dict] = []
    for row in payload.get("nodes") or []:
        if not isinstance(row, dict):
            continue
        mid = str(row.get("id") or "").strip()
        uid = str(row.get("user_id") or "").strip()
        text = str(row.get("text") or "").strip()
        if not mid or not uid or not text:
            continue
        out.append(
            {
                "id": mid,
                "user_id": uid,
                "excerpt": text[:380].replace("\n", " ").replace("\r", " "),
            }
        )
    return out


def _pair_batches(
    nodes: list[dict],
    *,
    max_pair: int,
    per_side: int,
) -> list[tuple[str, str, str]]:
    """Возвращает список (label_a, label_b, блок_текста_для_промпта)."""
    by_u: dict[str, list[dict]] = {}
    for n in nodes:
        by_u.setdefault(n["user_id"], []).append(n)

    uids = list(by_u.keys())
    projects = sorted([u for u in uids if u.startswith("project_")])
    global_ids = sorted([u for u in uids if u in ("global_skills", "global_topology")])

    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(projects):
        for b in projects[i + 1 :]:
            pairs.append((a, b))
    for g in global_ids:
        for p in projects:
            pairs.append((g, p))

    batches: list[tuple[str, str, str]] = []
    for a, b in pairs[:max(0, max_pair)]:
        rows_a = by_u.get(a, [])[:per_side]
        rows_b = by_u.get(b, [])[:per_side]
        if len(rows_a) < 1 or len(rows_b) < 1:
            continue

        def block(tag: str, rows: list[dict]) -> str:
            lines = [f"{r['id']}\t{r['user_id']}\t{r['excerpt']}" for r in rows]
            return tag + "\n" + "\n".join(lines)

        blob = (
            block(f"CHANNEL_A={a}", rows_a)
            + "\n\n"
            + block(f"CHANNEL_B={b}", rows_b)
            + "\n\nСопоставь только памяти из A с памятями из B (не внутри одного канала)."
        )
        batches.append((a, b, blob))
    return batches


def _build_prompt(channel_a: str, channel_b: str, blob: str) -> str:
    return f"""Ты анализируешь два канала памяти (разные области знаний/проекты).

Задача: найди пары или небольшие группы записей между каналом A и каналом B, где факт из одного канала полезно знать при работе в другом (общие технологии, контракты API, паттерны, терминология, смежные задачи).

Каналы: {channel_a}  ←→  {channel_b}

Данные (табуляция между полями: id \\t user_id \\t excerpt):
{blob}

Верни ТОЛЬКО валидный JSON-массив объектов, без текста до или после. Схема объекта:
{{
  "relation": один из строк: "one_to_one" | "one_to_many" | "many_to_one" | "many_to_many",
  "source_ids": ["uuid памяти-источника", ...],
  "target_ids": ["uuid памяти-получателя", ...],
  "benefits_user_ids": ["project_slug или global_skills/global_topology для кого главная польза"],
  "rationale_for_agent": "Коротко: почему эта связь полезна и как агенту использовать запись источника в контексте целевого проекта.",
  "confidence": число от 0 до 1
}}

Правила:
- Используй только id из таблицы выше (точное совпадение строк UUID).
- source_ids должны быть из одного канала, target_ids — из другого (не смешивай стороны).
- Если сомневаешься — не добавляй связь или поставь низкий confidence.
- Лимит не более 12 объектов на эту пару каналов.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Ollama: предложить cross-links между памятями проектов")
    ap.add_argument("--dry-run", action="store_true", help="Только показать пары и размер промпта, без Ollama")
    ap.add_argument("--apply", action="store_true", help="Вызвать Ollama и записать memory_cross_links.json")
    ap.add_argument("--max-pairs", type=int, default=30, help="Максимум пар каналов за запуск")
    ap.add_argument("--per-side", type=int, default=18, help="Макс. записей с каждой стороны в паре")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    ap.add_argument("--model", default=os.environ.get("OLLAMA_LLM", "llama3.2"))
    ap.add_argument(
        "--sync-mem0",
        action="store_true",
        help="После записи JSON: проставить metadata.cross_refs в Mem0 и опционально global_topology",
    )
    ap.add_argument(
        "--sync-mem0-no-topology",
        action="store_true",
        help="При --sync-mem0 не добавлять строки [CROSS_REF_AUTO] в global_topology",
    )
    args = ap.parse_args()

    if args.dry_run and args.apply:
        print("Укажите только один из: --dry-run или --apply", file=sys.stderr)
        return 2
    if not args.dry_run and not args.apply:
        print("Нужен --dry-run или --apply", file=sys.stderr)
        return 2

    payload = _fetch_all()
    if payload.get("error"):
        print("Ошибка загрузки данных:", payload["error"], file=sys.stderr)
        return 1

    nodes = _compact_nodes(payload)
    batches = _pair_batches(nodes, max_pair=args.max_pairs, per_side=args.per_side)
    print(f"Узлов с текстом: {len(nodes)} · пар каналов в очереди: {len(batches)}")

    if args.dry_run:
        for a, b, blob in batches[:5]:
            print(f"\n--- sample pair {a} x {b} · prompt chars ~ {_build_prompt(a, b, blob).__len__()}")
        if len(batches) > 5:
            print(f"... и ещё {len(batches) - 5} пар")
        return 0

    from autolinkingbrain.brain_link_store import load_cross_links

    doc = load_cross_links()
    total_new = 0
    for a, b, blob in batches:
        prompt = _build_prompt(a, b, blob)
        print(f"→ Ollama: {a} × {b} …", flush=True)
        try:
            raw = _ollama_generate(args.host, args.model, prompt)
        except urllib.error.URLError as e:
            print(f"   сеть/Ollama: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"   ошибка: {e}", file=sys.stderr)
            continue
        try:
            arr = _extract_json_array(raw)
        except Exception as e:
            print(f"   разбор JSON: {e}", file=sys.stderr)
            continue
        if not isinstance(arr, list):
            continue
        stamped = []
        for item in arr:
            if not isinstance(item, dict):
                continue
            item = dict(item)
            item.setdefault("source", f"ollama:{args.model}")
            stamped.append(item)
        doc, added = merge_edges(doc, stamped)
        total_new += added
        print(f"   принято новых рёбер: {added}")

    save_cross_links(doc)
    print(f"Готово. Всего добавлено уникальных рёбер в этом запуске: {total_new}")
    print(f"Файл: memory_cross_links.json (в корне {_SERVER_DIR})")

    if args.sync_mem0:
        import warnings

        from autolinkingbrain.cross_link_mem0_sync import sync_cross_links_document
        from mem0 import Memory
        from autolinkingbrain.mem0_settings import mem0_vector_config

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mm = Memory.from_config(config_dict=mem0_vector_config())
        stats = sync_cross_links_document(
            mm,
            doc,
            write_topology=not args.sync_mem0_no_topology,
        )
        print("Синхронизация Mem0:", json.dumps(stats, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
