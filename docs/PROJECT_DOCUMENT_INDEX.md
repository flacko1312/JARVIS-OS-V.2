# JARVIS Document Index

Navigation only. This file is not a second architecture, state, or backlog authority.

| Path | Purpose | Classification | Canonical authority | Maintained | Relationship / superseded by |
|---|---|---|---|---|---|
| `README.md` | Entry point and setup overview | CANONICAL ENTRY | Navigation/setup | Yes | Links to all canonical docs |
| `docs/ARCHITECTURE.md` | Current executable architecture | CANONICAL | Architecture | Yes | Code/tests/audit evidence |
| `docs/PROJECT_STATE.md` | Current verified status | CANONICAL | Current state | Yes | Audit snapshot provides evidence |
| `docs/TASKS.md` | Actionable backlog | CANONICAL | JARVIS tasks | Yes | Debt details in `TECHNICAL_DEBT.md` |
| `docs/CHANGELOG.md` | Recovery-level history | CANONICAL | Change summary | Yes | Git history is detailed evidence |
| `docs/TESTING.md` | Supported test and human-gate procedure | CANONICAL/OPERATIONAL | Validation | Yes | `docs/QA.md` supplies QA harness details |
| `docs/LILITH_INTEGRATION.md` | JARVIS-LILITH contract | CANONICAL | Integration | Yes | Must agree with LILITH ADR-037/API |
| `docs/TECHNICAL_DEBT.md` | Classified debt register | CANONICAL | Debt | Yes | Tasks reference debt IDs |
| `docs/audits/JARVIS_PROJECT_RECOVERY_2026-10-08.md` | Recovery evidence snapshot | AUDIT | 2026-10-08 facts | No, append corrections only | Supports state/architecture |
| `docs/QA.md` | Side-effect-safe QA operations | OPERATIONAL | QA harness | Yes | Does not replace test matrix |
| `docs/USAGE.md` | End-user capability guide | OPERATIONAL | Usage | Yes | Subject to executable architecture |
| `docs/TUTORIAL.md` | Installation/tutorial | OPERATIONAL | Onboarding | Yes | Historical wording should not define architecture |
| `DESIGN.md` | Current visual principles | REFERENCE | Design constraints | Yes | No first-run/tour product contract |
| `PRODUCT.md` | Product principles | REFERENCE | Product intent | Yes | Architecture/state win on implementation facts |
| `CONTRIBUTING.md` | Contribution process | OPERATIONAL | Contribution workflow | Yes | Test procedure in `docs/TESTING.md` |
| `docs/MEMORY.md` | Link/reference to earlier awareness note | HISTORICAL/REFERENCE | None | No | Superseded for authority by `ARCHITECTURE.md` and `LILITH_INTEGRATION.md` |
| `/home/flako1312/INTEGRACION/docs/CURRENT_STATE.md` | Cross-project integration state | EXTERNAL CANONICAL | Integration program state | External | JARVIS details defer to this repository |
| `/home/flako1312/INTEGRACION/docs/04_TASKS.md` | Cross-project tasks | EXTERNAL CANONICAL | Integration backlog | External | Do not duplicate into JARVIS tasks |
| `/home/flako1312/INTEGRACION/docs/02_PROJECT_STATE.md` | Older integration state | EXTERNAL HISTORICAL | None | No | Superseded by `CURRENT_STATE.md` |
| `/home/flako1312/INTEGRACION/docs/03_ROADMAP.md` | Older integration roadmap | EXTERNAL HISTORICAL | None | No | Superseded by `04_TASKS.md` |
| `/home/flako1312/lilith/docs/ADR/ADR-037*` | Canonical combined voice ownership decision | EXTERNAL CANONICAL | Global voice boundary | External | JARVIS architecture conforms |
| `/home/flako1312/lilith/docs/PROJECT_DOCUMENT_INDEX.md` | Cross-project top-level index | EXTERNAL CANONICAL | Cross-project navigation | External | This index provides JARVIS detail only |

Untracked prompts, pasted requests, generated `.qa-artifacts`, runtime logs, ignored `tmp/` snapshots, and private configuration are evidence or runtime state, not active documentation authority.
