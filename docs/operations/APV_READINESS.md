# APV Operational Readiness

- Last verified at (UTC): `2026-03-07 14:17`
- Verified by: `@LittleDevMars`
- Repository: `Code2731/FastMovieMaker`
- Secret (`APV_SAMPLE_B64`) status: `missing`
- Latest APV workflow run URL: `pending (secret not configured)`
- Latest `apv-smoke` conclusion: `SKIPPED (no sample injected)`
- `verify_apv_secret_ready.py` output:
  - `result: SKIPPED`
  - `reason: gh auth unavailable (local token invalid)`

## Checklist

- [ ] `APV_SAMPLE_B64` is configured in GitHub Actions secrets
- [ ] Recent 3 `apv-smoke` runs are `PASS`
- [ ] `python3 scripts/verify_apv_secret_ready.py` returns `PASS`
- [x] Evidence links are attached in this document

## Handoff Status

- Repository-side preparation is complete (`result/reason` format, soft/hard gate split, CI APV jobs separated).
- Remaining close-out actions require maintainer permissions:
  - Configure `APV_SAMPLE_B64`
  - Collect latest 3 successful `apv-smoke` run URLs
  - Re-run readiness check until `result: PASS`

## Verification Procedure

1. Configure `APV_SAMPLE_B64` in `Settings > Secrets and variables > Actions`.
2. Trigger `Tests` workflow (`workflow_dispatch`) and confirm `apv-operational-ready` job passes.
3. Run locally (with valid `gh` auth):
   - `python3 scripts/verify_apv_secret_ready.py`
   - `python3 scripts/verify_apv_secret_ready.py --require-pass`
4. Update this document with run URL and exact output summary.
