# AUT-11 — Static quality tooling

## Configuration

- Added reproducible `quality` optional dependencies: Ruff 0.17.x and mypy 2.4.x.
- Ruff baseline enables syntax/error checks, Pyflakes and import ordering without whole-project formatting churn.
- Incremental mypy scope is six completion-pass core modules: voice configuration, error reporting, local AI, provider status, development workspace and Gemini configuration.
- Imports are skipped for this first mypy boundary so legacy dependency typing does not turn into an implicit whole-project conversion.

## Results

- `ruff 0.17.0`: **All checks passed** for the six scoped core modules.
- `mypy 2.4.0`: **Success: no issues found in 6 source files**.
- Focused regression: **35 passed, 8 subtests passed**.

An exploratory wider Ruff scan found existing style and undefined-name debt outside the configured completion-pass scope. It was not mass-fixed because that would create unrelated churn. Notably, legacy `actions/tts_engine.py` still contains dormant external-provider references despite the active catalog being Gemini-only; this remains documented debt rather than being hidden with ignores.
