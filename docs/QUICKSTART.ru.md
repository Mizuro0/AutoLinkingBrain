# AutoLinkingBrain — быстрый старт

## 1. Установка

```powershell
cd d:\mcp_server
copy config\local\install.yaml.example config\local\install.yaml
# В install.yaml для своей машины: profile: full
python brain.py onboard
python brain.py doctor
```

Профили MCP: `minimal` (Brain), `standard` (+ QwenReviewer, **дефолт репо**), `full` (+ ArchitectureCurator).

Личный профиль — **не в git**: `config/local/install.yaml` (см. [config/local/README.md](../config/local/README.md)).  
`python brain.py mcp install` и `sync-agent` читают этот файл, если нет флага `--profile`.

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

## 5. Architecture по фичам (profile full)

Включите `profile: full` в `config/local/install.yaml` (или `python brain.py mcp install --profile full`).

MCP **ArchitectureCurator** + skill **`architecture-by-feature`** + rule `architecture-curator.mdc`.

Цикл на фичу: Brain recall → CodeGraph → `buildArchitectureContext` → `updateArchitectureSection` (одна секция за вызов) → `storeKnowledge`.

Файл: `{project}/docs/ARCHITECTURE.generated.md`

```powershell
python brain.py sync-agent --force-copy
```

## 6. Метрики

- **Локально:** `python brain.py start` → Ops (`O`), `python brain.py stats`
- **Fleet (admin):** `brain_fleet_server.py` на VPS, `python brain.py fleet push`

Подробнее: [AGENT_PROTOCOL.md](AGENT_PROTOCOL.md), [README.ru.md](README.ru.md).
