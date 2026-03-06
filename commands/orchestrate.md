# Orchestrate Command (FastMovieMaker)

Sequential workflow template for complex tasks in this repository.

## Usage

`/orchestrate [workflow-type] [task-description]`

## Workflow Types

### feature
For new feature implementation:
`planner -> implementer -> reviewer -> verifier`

### bugfix
For defect investigation and fixes:
`planner -> implementer -> reviewer`

### refactor
For safe internal cleanup:
`planner -> implementer -> reviewer -> verifier`

### quality
For quality hardening only:
`reviewer -> verifier -> planner`

## Handoff Format

```markdown
## HANDOFF: [from] -> [to]

### Task
[what was requested]

### Done
[what was completed]

### Findings
[key technical findings]

### Files
[changed/checked files]

### Open Items
[remaining risks or decisions]

### Next Action
[exact next step]
```

## Final Report Format

```text
ORCHESTRATION REPORT
Workflow: [type]
Task: [description]

Summary:
- [result 1]
- [result 2]

Files Changed:
- [path]

Checks:
- [command]: [pass/fail]

Recommendation:
- [SHIP / NEEDS WORK / BLOCKED]
```

## Notes

- Keep each handoff short and decision-focused.
- Use repository conventions from `AGENTS.md`, `CLAUDE.md`, `DECISION_TREE.md`.
- Prefer small, mergeable increments.
