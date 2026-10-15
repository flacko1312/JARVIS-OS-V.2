# AUT-13 — Final regression

## Exact current results

| Validation | Result |
|---|---|
| Complete pytest suite | **1059 passed, 93 skipped, 1 warning, 46 subtests passed** in 30.94 s |
| Python compileall | **PASS** |
| Ruff 0.17.0 scoped core | **PASS**, all checks passed |
| mypy 2.4.0 incremental scope | **PASS**, no issues in 6 source files |
| Web TypeScript (`tsc --noEmit`) | **PASS** |
| Web ESLint | **PASS** |
| Next.js 16.4.0 production build | **PASS**, static `/` and `/_not-found` generated |
| Safe self-test | **8 pass, 0 warning, 0 fail**; 4 supervised groups still required |
| Ten-second resource soak | **PASS**, 11 samples, 0 warnings |
| `git diff --check` | **PASS** |

The single pytest warning is the dependency's existing Google GenAI Python 3.17 deprecation warning. The suite retains 93 skips, equal to the source-of-truth baseline; the test diff adds no `skip` or `xfail` conversion.

## Review

- No tracked file deletion.
- No generated build output or `.qa-artifacts` was added to Git status.
- No credential-shaped values were found in the tracked diff scan.
- No real Gmail, Home Assistant, destructive developer command, push, microphone, camera or playback action was executed.
- Existing line-ending conversion notices remain Git configuration notices; whitespace validation passes.

Automated self-test output explicitly retains live-check requirements. This regression is not physical certification.
