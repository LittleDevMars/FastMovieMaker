# Orchestration Commands

Imported and adapted from:
- [everything-claude-code](https://github.com/affaan-m/everything-claude-code)

This project now includes lightweight command templates in `commands/`:

- `commands/orchestrate.md`
- `commands/plan.md`
- `commands/verify.md`

## How to use

1. Start planning:
   - `/plan [task]`
2. Execute multi-step delivery:
   - `/orchestrate feature [task]`
3. Validate before PR:
   - `/verify full`

## Why only these files

The upstream repository contains a full ecosystem (rules/hooks/plugins/agents).
For this project, only orchestration essentials were imported to avoid heavy process changes.
