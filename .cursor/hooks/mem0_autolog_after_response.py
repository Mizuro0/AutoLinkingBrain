"""
Cursor hook: afterAgentResponse — при важном ответе ассистента пишет сжатую запись в Mem0.

По умолчанию **Ollama** (`MEM0_AUTOLOG_USE_OLLAMA=1`) делает короткую выжимку фактов на английском; при сбое
или ответе NONE — откат на «строгий» отбор (`MEM0_AUTOLOG_STRICT=1`, см. MEM0_AUTOLOG_OLLAMA_FALLBACK).

Переменные: см. README (раздел про хук).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.getLogger("chromadb").setLevel(logging.ERROR)

_MIN_LEN = int(os.environ.get("MEM0_AUTOLOG_MIN_CHARS", "400"))
_MAX_BODY = int(os.environ.get("MEM0_AUTOLOG_MAX_CHARS", "10000"))
# При infer=True Mem0 гоняет текст через LLM — легко вылететь по context. Автолог пишет с infer=False (только эмбеддинг).
# Лимит всё равно нужен под окно эмбеддера (nomic и т.п. — ориентир ~8k токенов).
_MEM0_SAFE_CHARS = int(os.environ.get("MEM0_AUTOLOG_MEM0_SAFE_CHARS", "7500"))
_STRICT = os.environ.get("MEM0_AUTOLOG_STRICT", "1").strip().lower() not in ("0", "false", "no")
# По умолчанию дистилляция включена; MEM0_AUTOLOG_USE_OLLAMA=0 — только эвристики.
_USE_OLLAMA = os.environ.get("MEM0_AUTOLOG_USE_OLLAMA", "1").strip().lower() not in ("0", "false", "no")
_OLLAMA_FALLBACK = os.environ.get("MEM0_AUTOLOG_OLLAMA_FALLBACK", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
_OLLAMA_URL = os.environ.get("MEM0_AUTOLOG_OLLAMA_URL", "http://127.0.0.1:11434/api/generate").strip()
_OLLAMA_MODEL = os.environ.get("MEM0_AUTOLOG_OLLAMA_MODEL", "llama3.2").strip()
_OLLAMA_TIMEOUT = float(os.environ.get("MEM0_AUTOLOG_OLLAMA_TIMEOUT", "60"))
_OLLAMA_NUM_CTX = int(os.environ.get("MEM0_AUTOLOG_OLLAMA_NUM_CTX", "8192"))
# project | global | both — куда писать (global_skills = общий «навык» канал как в brain_server)
_TARGET = os.environ.get("MEM0_AUTOLOG_TARGET", "project").strip().lower()
_GLOBAL_ID = "global_skills"
_LOG_DIR = _ROOT / ".cursor"
_LAST_RUN = _LOG_DIR / "mem0_autolog_last.txt"
_APPEND_LOG = _LOG_DIR / "mem0_autolog_hook.log"
_MARKER_NAMES = ("mem0_autolog_debug.on",)


def _dedupe_path(project: str) -> Path:
    safe = re.sub(r"[^\w\-.]", "_", project)[:80]
    return _LOG_DIR / f"mem0_autolog_dedupe_{safe}.json"


def _dedupe_is_duplicate(project: str, payload: str) -> bool:
    """Не пишем тот же payload повторно в окне MEM0_AUTOLOG_DEDUPE_SEC (меньше дублей в Chroma и эмбеддингов)."""
    window = int(os.environ.get("MEM0_AUTOLOG_DEDUPE_SEC", "900"))
    if window <= 0:
        return False
    key = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()
    path = _dedupe_path(project)
    now = time.time()
    try:
        if path.is_file():
            prev = json.loads(path.read_text(encoding="utf-8"))
            if prev.get("h") == key and now - float(prev.get("t", 0)) < window:
                return True
    except Exception:
        pass
    return False


def _dedupe_mark_written(project: str, payload: str) -> None:
    window = int(os.environ.get("MEM0_AUTOLOG_DEDUPE_SEC", "900"))
    if window <= 0:
        return
    key = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()
    path = _dedupe_path(project)
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"h": key, "t": time.time()}), encoding="utf-8")
    except Exception:
        pass


def _debug_enabled() -> bool:
    """Cursor иногда не прокидывает env из hooks.json — можно включить маркером-файлом."""
    if os.environ.get("MEM0_AUTOLOG_DEBUG", "").strip().lower() in ("1", "true", "yes"):
        return True
    for name in _MARKER_NAMES:
        if (_LOG_DIR / name).exists():
            return True
        if (Path.home() / ".cursor" / name).exists():
            return True
    return False


def _debug(msg: str) -> None:
    if not _debug_enabled():
        return
    line = f"{datetime.now().isoformat()} {msg}\n"
    for log_path in (_APPEND_LOG, Path.home() / ".cursor" / "mem0_autolog_hook.log"):
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fp:
                fp.write(line)
        except Exception:
            continue


def _write_last_run(status: str, project: str, text_len: int, extra: str = "") -> None:
    """Один короткий файл на каждый вызов хука — видно даже без env и без ~/.cursor."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        line = (
            f"{datetime.now().isoformat()} status={status} project={project!r} "
            f"text_len={text_len} env_DEBUG={os.environ.get('MEM0_AUTOLOG_DEBUG', '')!r} {extra}\n"
        )
        with _LAST_RUN.open("w", encoding="utf-8") as fp:
            fp.write(line)
    except Exception:
        pass
    try:
        from autolinkingbrain.brain_metrics import log_hook

        log_hook("afterAgentResponse", status, project=project, text_len=text_len, extra=extra)
    except Exception:
        pass


# Сигналы «есть что запоминать» (RU/EN), если не используем Ollama-дистилляцию
_IMPORTANCE_PATTERNS = re.compile(
    r"(архитектур|миграц|контракт|endpoint|deprecat|решили|договорились|"
    r"используем\s+[A-Z]|Gradle|Koin|Dagger|Retrofit|Ktor|PostgreSQL|Mongo|Redis|"
    r"CI/CD|баг|bugfix|рефакторинг|refactor|breaking|API\s+v?\d|JSON\s+schema|"
    r"MCP|Mem0|Ollama|конфиг|\.env|security|уязвим|Spring|Kotlin|JPA|Flyway|"
    r"OpenAPI|монолит|репозитор|Elasticsearch|Kafka|OAuth|Orthanc|DICOM)",
    re.IGNORECASE,
)


def _code_fence_ratio(s: str) -> float:
    if not s.strip():
        return 0.0
    parts = re.split(r"```[\s\S]*?```", s)
    outside = "".join(parts)
    return 1.0 - (len(outside.strip()) / max(len(s.strip()), 1))


def _trivial_short_reply(s: str) -> bool:
    if len(s) > 900:
        return False
    low = s.lstrip().lower()
    prefixes = (
        "конечно",
        "хорошо",
        "окей",
        "ок ",
        "да,",
        "sure",
        "certainly",
        "of course",
        "here is",
        "вот ",
        "готово",
    )
    return any(low.startswith(p) for p in prefixes) and len(s) < 500


def _passes_strict_without_ollama(text: str) -> bool:
    if len(text) < _MIN_LEN:
        return False
    if _code_fence_ratio(text) > 0.82:
        return False
    if _trivial_short_reply(text):
        return False
    if _IMPORTANCE_PATTERNS.search(text):
        return True
    # обзор проекта в Markdown (типичный отчёт агента)
    if text.count("##") >= 2 and len(text) >= 600:
        return True
    # длинный связный ответ без явных ключей — допускаем как потенциально полезный
    if len(text) >= 2800 and text.count("\n") >= 8:
        return True
    return False


def _cap_body_for_mem0_llm(body: str) -> str:
    """Лимит длины перед mem.add (эмбеддер и на случай длинного fallback без дистилляции)."""
    if len(body) <= _MEM0_SAFE_CHARS:
        return body
    return (
        body[:_MEM0_SAFE_CHARS]
        + f"\n… [truncated for Mem0 LLM: was {len(body)} chars, cap={_MEM0_SAFE_CHARS}]"
    )


def _ollama_distill_facts(assistant_text: str) -> str | None:
    """Локальная Llama: выжимка фактов на английском для Mem0, или None."""
    snippet = assistant_text[:_MAX_BODY]
    prompt = (
        "You compress an assistant reply into durable engineering notes for a vector memory DB.\n"
        "Rules:\n"
        "- Output ONLY English.\n"
        "- If there is nothing worth long-term memory (small talk, pure code paste with no decision, "
        "  or empty content), output exactly one word on the first line: NONE\n"
        "- Otherwise output up to 8 bullet lines. Start each line with '- '. One fact per line.\n"
        "- Include: stack, decisions, bug causes/fixes, APIs, configs, security, migrations, file paths only if essential.\n"
        "- No greetings, no repetition of the full reply, no markdown headings.\n\n"
        f"Assistant reply:\n---\n{snippet}\n---\n\nYour output:"
    )
    payload = json.dumps(
        {
            "model": _OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.15,
                "num_predict": 700,
                "num_ctx": _OLLAMA_NUM_CTX,
            },
        }
    ).encode("utf-8")
    req = Request(_OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=_OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    out = (data.get("response") or "").strip()
    if not out:
        return None
    first_line = out.splitlines()[0].strip().upper()
    if first_line == "NONE" or first_line.startswith("NONE "):
        return None
    if out.upper().startswith("NONE\n"):
        return None
    return out.strip()


def _body_from_heuristics(assistant_text: str) -> str | None:
    """Текст для Mem0 без Llama: строгий/нестрогий фильтр и обрезка."""
    if not _STRICT:
        if len(assistant_text) < _MIN_LEN:
            return None
        body = assistant_text[:_MAX_BODY]
        if len(assistant_text) > _MAX_BODY:
            body += "\n… [truncated]"
        return body
    if not _passes_strict_without_ollama(assistant_text):
        return None
    body = assistant_text[:_MAX_BODY]
    if len(assistant_text) > _MAX_BODY:
        body += "\n… [truncated]"
    return body


def _user_ids_for_write(project: str) -> list[str]:
    if _TARGET == "global":
        return [_GLOBAL_ID]
    if _TARGET == "both":
        return [f"project_{project}", _GLOBAL_ID]
    return [f"project_{project}"]


def main() -> None:
    if os.environ.get("MEM0_AUTOLOG", "1").strip().lower() in ("0", "false", "no"):
        _write_last_run("disabled_autolog", "n/a", 0)
        _debug("skip MEM0_AUTOLOG=0")
        print("{}")
        return

    try:
        raw_bytes = sys.stdin.buffer.read()
    except Exception as e:
        _write_last_run("stdin_read_error", "n/a", 0, extra=repr(e)[:120])
        print("{}")
        return

    if not raw_bytes.strip():
        _write_last_run("empty_stdin", "n/a", 0, extra=f"argv={sys.argv[1:]!r}")
        _debug("skip empty stdin")
        print("{}")
        return

    try:
        raw = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw = raw_bytes.decode("utf-8", errors="replace")

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        dump = _LOG_DIR / "mem0_autolog_stdin.txt"
        with dump.open("w", encoding="utf-8") as fp:
            fp.write(raw)
    except Exception:
        pass

    try:
        data = json.loads(raw)
    except Exception as e:
        preview = raw.strip().replace("\n", " ")[:200]
        _write_last_run(
            "json_error",
            "n/a",
            len(raw),
            extra=f"err={repr(e)[:120]} preview={preview!r} argv={sys.argv[1:]!r}",
        )
        _debug(f"skip json error {e!r} preview={preview!r}")
        print("{}")
        return

    text = (data.get("text") or "").strip()
    if len(text) < 80:
        _write_last_run("text_too_short", "n/a", len(text))
        _debug(f"skip text too short len={len(text)}")
        print("{}")
        return

    roots = data.get("workspace_roots") or []
    cwd = str(data.get("cwd") or "")
    from autolinkingbrain.mem0_project_slug import extract_context_paths_from_text, resolve_project_slug

    ctx = ""
    for p in extract_context_paths_from_text(text, limit=5):
        ctx = p
        break
    project = resolve_project_slug(
        context_path=ctx,
        workspace_roots=roots if isinstance(roots, list) else None,
        cwd=cwd or None,
    )

    body_to_store: str | None = None
    from_ollama = False
    ollama_min = int(os.environ.get("MEM0_AUTOLOG_OLLAMA_MIN_CHARS", "200"))

    if _USE_OLLAMA:
        if len(text) >= ollama_min:
            body_to_store = _ollama_distill_facts(text)
            if body_to_store:
                from_ollama = True
            elif _OLLAMA_FALLBACK:
                body_to_store = _body_from_heuristics(text)
                _debug(f"ollama NONE/fail → heuristic fallback project={project} len={len(text)}")
        elif _OLLAMA_FALLBACK:
            body_to_store = _body_from_heuristics(text)
            _debug(f"short text → heuristic fallback len={len(text)} project={project}")
        else:
            _write_last_run("skip_ollama_minlen", project, len(text))
            _debug(f"skip ollama path short len={len(text)} project={project} fallback=off")
            print("{}")
            return
    else:
        if not _STRICT:
            if len(text) < _MIN_LEN:
                _write_last_run("skip_minlen", project, len(text))
                _debug(f"skip non-strict short len={len(text)} project={project}")
                print("{}")
                return
            body_to_store = text[:_MAX_BODY]
            if len(text) > _MAX_BODY:
                body_to_store += "\n… [truncated]"
        else:
            if not _passes_strict_without_ollama(text):
                _write_last_run("skip_strict_filter", project, len(text))
                _debug(
                    f"skip strict_filter project={project} len={len(text)} "
                    f"code_ratio={_code_fence_ratio(text):.2f}"
                )
                print("{}")
                return
            body_to_store = text[:_MAX_BODY]
            if len(text) > _MAX_BODY:
                body_to_store += "\n… [truncated]"

    if not body_to_store:
        if _USE_OLLAMA:
            _write_last_run("skip_ollama_none_no_fallback", project, len(text))
            _debug(f"skip ollama NONE and heuristic miss project={project} len={len(text)}")
        print("{}")
        return

    assert body_to_store is not None
    body_to_store = _cap_body_for_mem0_llm(body_to_store)

    from autolinkingbrain.mem0_privacy import prepare_for_storage, should_block_write
    from autolinkingbrain.mem0_provenance import stamp_provenance

    body_to_store, _ = prepare_for_storage(body_to_store)
    if should_block_write(body_to_store):
        _write_last_run("skip_privacy_block", project, len(text))
        _debug(f"skip privacy block project={project}")
        print("{}")
        return

    cid = str(data.get("conversation_id") or "")[:12]
    gid = str(data.get("generation_id") or "")[:12]
    model = str(data.get("model") or "")
    now = datetime.now().isoformat()
    if from_ollama:
        tag = "[CURSOR] [AUT_LOG_LLAMA]"
    elif _USE_OLLAMA:
        tag = "[CURSOR] [AUT_LOG_HEURISTIC_FALLBACK]"
    else:
        tag = "[CURSOR] [AUT_LOG]"
    line = (
        f"{tag} (Updated: {now}): "
        f"conversation={cid} generation={gid} model={model}\n"
        f"---\n{body_to_store}"
    )
    line, _ = prepare_for_storage(line)
    prov_detail = f"tag={tag.strip('[]')}"
    if model:
        prov_detail += f" model={model}"
    line = stamp_provenance(line, "hook:afterAgentResponse", detail=prov_detail)

    if _dedupe_is_duplicate(project, line):
        _write_last_run("skip_dedupe", project, len(text))
        _debug(f"skip dedupe same payload window project={project}")
        print("{}")
        return

    try:
        from mem0 import Memory

        from autolinkingbrain.mem0_settings import mem0_vector_config

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mem = Memory.from_config(config_dict=mem0_vector_config())
        uids = _user_ids_for_write(project)
        for uid in uids:
            # infer=False: без LLM-извлечения — длинный обзор не бьётся о context length llama3.2
            mem.add(line, user_id=uid, infer=False)
        try:
            from autolinkingbrain.mem0_hybrid_search import invalidate_channel_cache

            for uid in uids:
                invalidate_channel_cache(uid)
        except Exception:
            pass
        try:
            from autolinkingbrain.mem0_kb_log import log_mem0

            log_mem0(
                "write",
                "hook.afterAgentResponse.mem_add",
                user_ids=uids,
                infer=False,
                tag=tag,
                stored_chars=len(line),
            )
        except Exception:
            pass
        _dedupe_mark_written(project, line)
        _write_last_run("ok_wrote", project, len(text), extra=f"uids={uids}")
        _debug(f"OK wrote len={len(line)} uids={uids} project={project}")
    except Exception as e:
        _write_last_run("mem0_add_failed", project, len(text), extra=repr(e)[:200])
        _debug(f"FAIL mem0 add {e!r} project={project}")

    print("{}")


if __name__ == "__main__":
    main()
