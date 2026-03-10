# Plan Command (FastMovieMaker)

Create a concrete implementation plan before coding.

## Usage

`/plan [task-description]`

## What this does

1. Restates requirements.
2. Identifies risks and constraints.
3. Produces phased, file-level implementation steps.
4. Defines tests and acceptance criteria.

## Required Output Structure

```markdown
# Implementation Plan: [title]

## Summary
[2-3 sentences]

## Scope
- In: [...]
- Out: [...]

## Architecture Impact
- [file path]: [change]

## Steps
1. [step]
2. [step]

## Tests
- [test command]

## Risks
- [risk]: [mitigation]

## Acceptance Criteria
- [ ] ...
```

## Project Defaults

- Time units: milliseconds (`int`) for timeline/subtitle internals.
- Controllers/UI thread safety rules must be preserved.
- Prefer incremental changes with fast local verification.
