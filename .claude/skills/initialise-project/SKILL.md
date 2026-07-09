---
name: initialise-project
description: Bootstrap a new Claude Code project by copying the standard folder structure from the CDV_2 template. Copies .claude/ (skills, agents, hooks, settings), .claude-flow/, .swarm/, .mcp.json, .cursor/, CLAUDE.md, and .gitignore. Use whenever starting a new project, initialising a new repo, or setting up a new project folder that needs the full Claude Code + claude-flow stack.
---

# Project Bootstrap

Copies the full Claude Code project starter structure from the CDV_2 template into a new (or existing empty) project folder.

## What gets copied

| Item | Purpose |
|---|---|
| `.claude/` | Skills, agents, commands, helpers, hooks, settings |
| `.claude-flow/` | Claude-flow runtime: config, workflows, learning, sessions |
| `.swarm/` | Swarm memory DB and schema |
| `.mcp.json` | MCP server definitions (claude-flow, ruv-swarm, flow-nexus) |
| `.cursor/` | Cursor IDE MCP config |
| `CLAUDE.md` | Project rules and agent coordination config |
| `.gitignore` | Git ignore rules |

## How to use this skill

When the user asks to bootstrap or start a new project:

1. **Ask for the target path** if not already provided:
   - "What is the path or name for the new project?" 
   - If just a name is given (e.g. `My_Project`), place it under the default projects directory: `c:/Users/luidpv/OneDrive - Henkel/Documents/GitHub_personal/`

2. **Confirm** the resolved target path with the user before proceeding.

3. **Run the bootstrap script**:
   ```bash
   bash "c:/Users/luidpv/OneDrive - Henkel/Documents/GitHub_personal/CDV_2/.claude/skills/project-bootstrap/scripts/bootstrap.sh" "<target_path>"
   ```

4. **Report** what was copied and confirm the project is ready.

## Template source

The template is always read from:
```
c:/Users/luidpv/OneDrive - Henkel/Documents/GitHub_personal/CDV_2/
```

To change the template source, update `TEMPLATE_SRC` at the top of `scripts/bootstrap.sh`.

## Notes

- The script will **not overwrite** existing files — it skips items already present in the target.
- It creates the target directory if it does not exist.
- `workflows/` is intentionally excluded (n8n-specific, not general-purpose).
