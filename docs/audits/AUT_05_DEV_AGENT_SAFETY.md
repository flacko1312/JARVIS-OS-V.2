# AUT-05 — DEVELOPMENT AGENT SAFETY & CAPABILITY

**Date:** 2026-10-15

## Safety changes

- Screen-debug never overwrites the source from model output. It writes a unified patch proposal under `.jarvis-proposals`, records the original SHA-256 and returns a random approval token.
- Applying a screen fix is a separate `apply_screen_fix` call. The token is single-use, expires after 15 minutes and fails closed if the source changed after analysis.
- Dev Agent file creation/fix paths resolve through project-root containment; absolute and `..` escapes are rejected.
- Subprocess timeouts remain bounded.
- ImportError classification now distinguishes `cannot import name` from a genuinely missing module.

## Capability changes

- Project planning now requires a focused automated test file and `test_command`.
- Generated-project success requires both the run command and generated test command to pass; test failures enter the existing bounded auto-fix loop and appear in the final failure report.
- Controlled local Git support: status, diff, current branch, optional local branch creation and optional commit.
- Git commit never stages files; it commits only paths already staged by the user/workflow. No push, reset, checkout of existing branches or discard action exists.
- Git operations require an existing absolute approved project root and use bounded subprocess execution.

## Files changed

- `core/dev_workspace.py` (new)
- `actions/dev_agent.py`
- `actions/code_helper.py`
- `main.py`
- `tests/test_aut05_dev_agent_safety.py` (new)
- `tests/test_block4_codex_code.py` (corrected classification expectation)

## Validation

```text
73 passed, 0 failed, 3 skipped, 6 subtests passed
```

Git tests used disposable temporary repositories only. No important project was modified, no dependency was installed and no command was pushed.

## Remaining physical boundary

Real model-generated project quality, an owner-approved patch review and installed IDE/toolchain behavior remain **PHYSICAL TEST REQUIRED**.
