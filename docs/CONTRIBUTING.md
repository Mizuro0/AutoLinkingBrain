# Contributing

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
# Reproducible / CI-equivalent:
# pip install -r requirements-lock.txt
python -m pytest tests/ -q
```

Refresh lock after bumping direct pins in `requirements.txt`:

```powershell
.\scripts\regenerate_requirements_lock.ps1
```

CI (`.github/workflows/ci.yml`) runs the same on Ubuntu for every push/PR to `main`.

## Documentation coverage — what to aim for

This project is small and operator-focused. **100% line documentation is not the goal.** Reasonable targets:

| Area | Ideal coverage | Notes |
|------|----------------|-------|
| **`autolinkingbrain/**/*.py`** | **100%** module docstrings | Public library — every file explains its role |
| **Architecture layers** | **≥80%** with a README or `docs/` section | Root, package, hooks, viewer_web, scripts |
| **Entry points** | README + ARCHITECTURE | `brain.py`, `brain_server.py`, `viewer_server.py` |
| **Optional / legacy** | Marked deprecated | `viewer.py`, Streamlit, `requirements-legacy.txt` |
| **Line / API docstrings** | Add when behavior is non-obvious | Privacy rules, slug priority, RRF — not every helper |

The `tests/test_doc_coverage.py` guard encodes the minimum bar (module docstrings + required README files). It does **not** measure comment density.

## Adding features

- Mem0 logic → `autolinkingbrain/`
- MCP tools → `autolinkingbrain/mcp_tools/` (+ shared helpers in `mcp_context.py`)
- Viewer API → `viewer_server.py`; UI → `viewer_web/`
- Update tests when changing slug, privacy, link store, or fetch payload shape

## Legacy Streamlit viewer

Do not extend `viewer.py` for new features. Use Brain Viewer (`viewer_server` + `viewer_web`).

Optional install: `pip install -r requirements-legacy.txt`
