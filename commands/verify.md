# Verify Command (FastMovieMaker)

Run verification checks for current repository state.

## Usage

`/verify [quick|full|pre-pr]`

## Default Order

1. `git status --short`
2. `ruff check src tests` (if ruff is installed)
3. `QT_QPA_PLATFORM=offscreen pytest tests/ -q`
4. `python3 scripts/sync_test_counts.py --check`

## Output Format

```text
VERIFICATION: [PASS/FAIL]

Git:      [OK/ISSUES]
Lint:     [OK/X issues]
Tests:    [X/Y passed]
DocsSync: [OK/FAIL]

Ready for PR: [YES/NO]
```

## Mode Notes

- `quick`: run `git status`, targeted tests only.
- `full`: run full order above.
- `pre-pr`: full + summarize high-risk areas touched.
