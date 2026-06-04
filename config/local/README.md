# Local install (per machine)

Files here configure **your** Cursor MCP profile without changing the repo default (`standard`).

| File | In git? | Purpose |
|------|---------|---------|
| `install.yaml.example` | yes | Template |
| `install.yaml` | **no** (gitignored) | Your profile (`full`, `standard`, …) |

## Quick setup (ArchitectureCurator on one machine)

```powershell
cd D:\mcp_server
copy config\local\install.yaml.example config\local\install.yaml
# Edit install.yaml: profile: full
python brain.py mcp install
python brain.py sync-agent --force-copy
```

Reload MCP in Cursor. You should see **ArchitectureCurator** in addition to AutoLinkingBrain and QwenReviewer.

Override path: `BRAIN_LOCAL_INSTALL_YAML=C:\path\to\install.yaml`

Global TOML (`%APPDATA%\autolinkingbrain\config.toml`) remains optional for chroma/ollama; MCP profile for this repo is driven by `install.yaml` when CLI flags are omitted.
