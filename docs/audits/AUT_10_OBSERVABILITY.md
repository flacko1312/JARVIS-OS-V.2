# AUT-10 — Error handling and observability

## Outcome

- Added a shared error model with categories for authentication, configuration, timeouts, availability, rate limits, validation and internal errors.
- Added bounded diagnostic sanitization for common API keys, bearer values, tokens, secrets and passwords.
- Added correlation references to generic Gmail API failures while retaining the existing specific recovery messages for revoked credentials, permission denial and rate limiting.
- WebSocket-visible logs are sanitized before persistence/queueing.
- Reviewed priority paths. Ollama already uses narrow HTTP/timeout handling and generic Spanish error output; LILITH already logs exception types rather than secret-bearing exception bodies. Broad catches around optional UI/hardware probes were retained where graceful degradation is intentional.

## Validation

`python -m pytest tests/test_aut10_observability.py tests/test_aut02_local_ai_offline.py tests/test_aut06_gmail_complete.py tests/test_hosted_api.py tests/test_lilith_runtime_wiring.py -q`

Result: **79 passed, 1 warning, 2 subtests passed**.
