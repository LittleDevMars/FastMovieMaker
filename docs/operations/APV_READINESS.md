# APV Operational Readiness

- Last verified at (UTC): `YYYY-MM-DD HH:MM`
- Verified by: `@owner`
- Repository: `owner/repo`
- Secret (`APV_SAMPLE_B64`) status: `configured | missing`
- Latest APV workflow run URL: `https://github.com/<owner>/<repo>/actions/runs/<id>`
- Latest `apv-smoke` conclusion: `PASS | FAIL | SKIPPED`
- `verify_apv_secret_ready.py` output:
  - `result: PASS | SKIPPED | FAIL`
  - `reason: <one-line reason>`

## Checklist

- [ ] `APV_SAMPLE_B64` is configured in GitHub Actions secrets
- [ ] Recent 3 `apv-smoke` runs are `PASS`
- [ ] `python3 scripts/verify_apv_secret_ready.py` returns `PASS`
- [ ] Evidence links are attached in this document

## Verification Procedure

1. Configure `APV_SAMPLE_B64` in `Settings > Secrets and variables > Actions`.
2. Trigger `Tests` workflow (`workflow_dispatch`) and confirm `apv-operational-ready` job passes.
3. Run locally (with valid `gh` auth):
   - `python3 scripts/verify_apv_secret_ready.py`
   - `python3 scripts/verify_apv_secret_ready.py --require-pass`
4. Update this document with run URL and exact output summary.
