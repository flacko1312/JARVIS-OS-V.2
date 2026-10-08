# Memory Documentation

Classification: **REFERENCE**. Canonical memory authority is defined in `ARCHITECTURE.md` and `LILITH_INTEGRATION.md`.

- LILITH is the sole authoritative persistent personal memory.
- JARVIS `save_memory` is explicit local/session-only in-process state and does not survive a `JarvisLive` restart.
- Legacy JSON memory helpers remain compatibility code and must not receive user-requested persistent facts.
- [Awareness Engine Enhanced with VS Code and Related Project Detection](memory/awareness-engine-enhanced.md) is a historical awareness note, not a persistent-memory authority definition.
