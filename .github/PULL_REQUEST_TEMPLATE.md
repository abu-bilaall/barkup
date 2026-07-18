title: [Test 01] - add missing unit tests

### Description
Closes the Phase 0 coverage gap called out in `IMPLEMENTATION-PLAN.md`: several already-implemented modules had no unit tests. Writing those tests surfaced real defects, which are fixed here alongside the missing coverage.

### Type of Change
- [x] Bug fix (non-breaking)
- [x] Tests
- [x] Documentation
- [x] Chore / tooling

### Changes Made
- Add unit tests for `exclude_patterns` (`scan_sources`, `should_exclude`, `resolve_excluded`), `dry_run` (`dry_run_output`, `dry_local_run`, `dry_cloud_run`), `config_resolvers` (`resolve_local_config`, `resolve_cloud_config`), and `main` (Pydantic `ValidationError` handling). 73 tests now pass.
- Fix defects found while testing: make `ResolvedCloudConfig.credentials_file`/`remote_folder` optional (`str | None`) to match `CloudProvider`; stop shadowing the `files` parameter in `dry_run_output`'s inner loop; wire missing DB/cloud imports and `str()`-wrap the destination in `run_barkup`.
- Add `[tool.pyright]` (`extraPaths=["src"]`, `typeCheckingMode="standard"`) and ruff/type annotations so the editor is clean; add `black` to dev deps.
- Add `.github/PULL_REQUEST_TEMPLATE.md`.

### Testing
- [x] `uv run pytest -v` passes (73 tests)
- [x] New functionality has unit tests (deterministic, isolated, deps mocked)
- [x] `ruff check` is clean

