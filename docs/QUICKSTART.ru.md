# AutoLinkingBrain — быстрый старт

## 1. Установка

```powershell
cd d:\mcp_server
python brain.py onboard --host cursor --mcp-scope global --profile standard
python brain.py doctor
```

Профили: `minimal` (только Brain), `standard` (+ QwenReviewer), `full` (+ ArchitectureCurator).

## 2. MCP scope

| Scope | Файл |
|-------|------|
| `global` | `~/.cursor/mcp.json` |
| `project` | `{repo}/.cursor/mcp.json` |

```powershell
python brain.py mcp status
python brain.py mcp install --scope project --project-root D:\codes\backend
```

## 3. Переиндексация проекта

1. `checkProjectHealth` в Cursor
2. При `REINDEX_PROTOCOL: required` — scan → `storeKnowledge` → `markIndexingComplete`
3. При `ANALYSIS STATUS: required_*` — `runProjectAnalysis` (AUTO_RUN)

CLI:

```powershell
python brain.py health --project-root D:\codes\backend
python brain.py analyze auto --project-root D:\codes\backend --once
```

## 4. Knowledge GC

```powershell
python brain.py gc audit --project-root D:\codes\backend
python brain.py gc purge --confirm-token TOKEN --apply
```

## 5. Architecture (profile full)

MCP **ArchitectureCurator**: `getArchitectureDoc`, `updateArchitectureSection`.

Файл: `{project}/docs/ARCHITECTURE.generated.md`

## 6. Метрики

- **Локально:** `python brain.py start` → Ops (`O`), `python brain.py stats`
- **Fleet (admin):** `brain_fleet_server.py` на VPS, `python brain.py fleet push`

Подробнее: [AGENT_PROTOCOL.md](AGENT_PROTOCOL.md), [README.ru.md](README.ru.md).
