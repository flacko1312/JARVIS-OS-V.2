# JARVIS Test Matrix

Updated: 2026-10-08.

This file defines the supported test procedure for the current Linux recovery environment and the remaining Windows/audio gates. It does not replace `docs/QA.md`; it scopes which tests are expected to run where.

## 1. Linux Platform-Independent Baseline

Run on Linux without GUI/audio hardware assumptions:

```bash
python3 -m pytest -q tests/test_lilith_home_resolution.py
```

Current verified result: `33 passed`.

This slice covers LILITH home/memory routing safety with fake clients and no network, no Gemini, no real devices and no microphone.

## 2. Linux Stubbed Gemini/Audio Slices

Some Gemini Live tool tests import `sounddevice` and `google.genai`. In this Linux recovery host, full collection is not the supported baseline because PortAudio and the Google GenAI runtime are not guaranteed.

Supported recovery evidence uses temporary in-process stubs only for targeted, platform-independent behavior:

- `TestPersistentMemoryFlow`
- `TestMemoryCanonicalization`

Current verified recovery result: `23 passed, 4 subtests passed` with temporary `sounddevice` and `google.genai` stubs.

Do not report the whole `tests/test_lilith_gemini_tools.py` file as Linux-supported until dependency and event-loop behavior are normalized.

## 3. Hosted/API and Non-GUI Unit Tests

These tests require normal Python dependencies from `requirements.txt` and may need service/test configuration:

- `tests/test_hosted_api.py`
- `tests/test_deep_research.py`
- `tests/test_presentation_maker.py`
- other non-GUI unit tests that do not instantiate PyQt windows or audio devices

They are not part of the minimal LILITH recovery baseline. Run them when changing hosted API, research, presentation, or related subsystems.

## 4. UI Tests

Tests importing PyQt6 or creating widgets require a GUI-capable environment or a configured headless Qt setup:

- `tests/test_ui_regressions.py`
- `tests/test_graphics_quality.py`
- `tests/test_vision_preview.py`
- `tests/test_research_progress_ui.py`
- `tests/test_ui_branding.py`

They are not expected to pass in a bare SSH/Linux recovery shell unless the Qt/headless display environment is explicitly prepared.

## 5. Windows Runtime Tests

The real deployment target may exist at `C:\JARVIS`. From this Linux host, `/mnt/c/JARVIS` is inaccessible, so Linux cannot prove the Windows runtime is identical to this checkout.

Windows validation must be run on the actual Windows runtime after pulling `origin/main`:

```powershell
python -m pytest -q tests
```

For LILITH/JARVIS integration work, also run the focused Windows suites documented in `docs/LILITH_INTEGRATION.md`. Prior JL-A10 evidence recorded 126 Windows tests passing, but that does not replace future validation after new changes.

## 6. Human / Hardware Gates

These cannot be marked PASS from Linux:

- Opening the real Windows GUI.
- Speaking the JL-A9/JL-A10 routine phrases through the real microphone.
- Confirming Gemini Live interpretation and response in the live GUI.
- Any test that depends on a physical audio input/output path.
- Verifying that the Windows runtime at `C:\JARVIS` is identical to this Linux checkout
  when `/mnt/c/JARVIS` is inaccessible.

Report them as `EXPECTED HARDWARE GATE` until actually performed on the Windows machine.

## 6A. Voice Architecture Scope

The current primary voice/conversation interface is JARVIS + Gemini Live. Do not copy
LILITH-native wake-word, Whisper or local STT parameters into JARVIS test expectations.
Those LILITH-native components are deferred/future/fallback work and are tested only in
their own project scope if reactivated.

## 6B. Minimal Windows Gemini Live Human Validation

This gate must be performed on the real Windows machine, not from Linux.

1. Open a PowerShell terminal.
2. Go to the Windows runtime:

```powershell
cd C:\JARVIS
git pull --ff-only origin main
python -m pytest -q tests
python main.py
```

3. Expected startup result:

- The JARVIS GUI opens without traceback.
- Gemini Live connects after the configured Gemini API key is available.
- The selected audio output can be heard.
- The microphone permission prompt, if any, is accepted.

4. Spoken commands to test through the real microphone:

- "Hola JARVIS, dime que estás conectado."
- "¿Qué rutinas tengo programadas?"
- "Crea una rutina para encender la bombilla del mueble todos los días a las nueve de la noche."
- "Enséñame mis rutinas."
- "Borra la rutina que acabas de crear."

5. Evidence that proves success:

- Console/HUD log shows the spoken transcript.
- Gemini Live responds audibly and/or with visible transcript.
- For routine commands, logs show `lilith_routine` or the canonical command path, not `lilith_home_action` for recurring routine creation.
- LILITH returns a completed result for create/list/delete before JARVIS claims success.
- No traceback, reconnect loop, or false success appears.

6. PASS criteria:

- GUI opens.
- Microphone captures speech.
- Gemini Live understands the spoken phrases.
- JARVIS calls the correct LILITH tools.
- LILITH confirms completed results.
- JARVIS responds naturally after verified results.

7. FAIL criteria:

- GUI cannot start.
- Microphone/audio is unavailable.
- Gemini Live does not connect.
- A recurring routine is routed as an immediate Home Assistant action.
- JARVIS claims success while LILITH returned blocked/error/offline.
- Any traceback or unbounded reconnect loop occurs.

8. Evidence to send back:

- Exact command output from PowerShell.
- Screenshot or copied HUD/console transcript around the test.
- Any traceback.
- The spoken command that failed and the observed JARVIS response.

## 7. Reporting Rules

- Record exact command, environment and result.
- Separate `PRODUCT BUG`, `TEST BUG`, `STALE TEST`, `ENVIRONMENT BUG`, `DEPENDENCY BUG`, `PLATFORM-SPECIFIC`, `EXPECTED HARDWARE GATE` and `UNKNOWN`.
- Do not hide failures by skipping tests.
- Do not treat temporary import stubs as proof that the full live dependency stack works.
- Do not claim `C:\JARVIS` is synced unless verified on Windows.
