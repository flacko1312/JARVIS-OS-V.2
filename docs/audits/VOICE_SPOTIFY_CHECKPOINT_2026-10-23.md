# Voice / Spotify checkpoint — 2026-10-23

Status: **RECOVERABLE WORKING CHECKPOINT — NOT COMMITTED**

This checkpoint records the current good voice state after physical testing. It deliberately separates owner-validated behavior from automatic/offline evidence.

## Current runtime configuration

- `JARVIS_SPOTIFY_FILTER_MODE=shadow_v4`
- `JARVIS_SPOTIFY_PAUSE_GUARD_MS=350`
- `JARVIS_LIVE_VAD_SILENCE_MS=2500`
- Gemini Live model: `gemini-2.5-flash-native-audio-preview-12-2025`
- Input: Trust 1080P Webcam microphone.
- AURORA speech output remains on preferred `M197WD`.
- Spotify reference is captured per-process with the Windows process-loopback helper.

## Physically validated as good

### Natural pause / end-of-turn timing — PASS

The previous 320/650/1000/2000 ms end-of-turn values cut natural speech too early. At **2500 ms**, the owner completed a long, hesitant spoken sentence while thinking between phrases without AURORA splitting it into multiple turns. Do not increase this unless the owner again reports premature cuts; increasing it further only delays response start.

### Input transcription assembly — PASS for the observed regression

The visual transcript previously inserted artificial spaces inside words (`Ex plí ca me`, `di ferencia`, etc.) even when Gemini understood the audio correctly. The input-transcription merger now preserves provider token/word-boundary whitespace. Physical follow-up showed normal joined words instead of the prior systematic token splitting.

### Pending repeated request suppression — PASS

Repeated identical speech while the first request is still unanswered is absorbed using explicit pending-turn state. The same request is allowed again after the assistant response has started.

## Spotify filtering — current state

### Previous failure

`shadow_v1`/`shadow_v2`/`shadow_v3` still allowed Spotify speech/ads to be treated as near speech. Real false user turns included fragments such as `.`, `Where`, and `con todo`. A simple VAD cannot distinguish the owner from a singer/announcer because both are human speech.

### `shadow_v4` design

`shadow_v4` keeps the owner microphone PCM unmodified when near speech is accepted. Spotify is used only as a reference/analyser.

The v4 analyser:

1. keeps a short Spotify process-loopback reference window;
2. searches 0–160 ms in 10 ms steps for the reference segment that best correlates with the microphone block;
3. runs WebRTC AEC3 against the aligned reference;
4. combines AEC residual/retention, VAD probability, and Spotify correlation to decide whether independent near speech exists;
5. suppresses Spotify-only audio while preserving the original owner PCM when the near-speech gate opens.

This avoids the rigid FIFO reference alignment that caused spoken Spotify ads to survive the earlier filter.

### Evidence for v4

- Existing physical Spotify-only capture replayed through v4: **0 false gate-open sequences**.
- Example final offline metrics on a Spotify-only block: alignment correlation ~0.375, alignment lag ~130 ms, retention ~0.217, VAD ~0.576, gate closed.
- Full repository suite after v4 + configurable VAD test updates: **1235 passed, 93 skipped, 1 third-party warning, 49 subtests passed, 0 failures**.

### Physical status of v4

**PENDING PHYSICAL ACCEPTANCE.** The owner has not yet completed the final dedicated spoken-ad/music test after loading `shadow_v4`. Do not mark Spotify filtering physically passed until a real Spotify ad/song runs with the owner silent and produces zero user turns/responses, followed by an owner-over-Spotify speech test that is accepted normally.

## Rollback / isolation

The Spotify filter remains isolated behind one environment setting:

- `JARVIS_SPOTIFY_FILTER_MODE=off` — absolute bypass / no Spotify filter.
- `shadow_v1` — original experimental gate.
- `shadow_v2` — Spotify suppression represented as realtime digital silence.
- `shadow_v3` — adds short pause guard.
- `shadow_v4` — aligned-reference correlation + AEC classifier; current mode.

The end-of-turn delay is separately controlled by `JARVIS_LIVE_VAD_SILENCE_MS` and is bounded in code to 250–3000 ms.

## Recovery material

No commit was created because the repository already contains unrelated dirty work.

Checkpoint material:

- `C:\JARVIS\tmp\checkpoints\voice_runtime_tracked_2026-10-23.patch`
- `C:\JARVIS\tmp\checkpoints\voice_spotify_2026-10-23\spotify_aec.py`
- `C:\JARVIS\tmp\checkpoints\voice_spotify_2026-10-23\test_spotify_aec.py`
- `C:\JARVIS\tmp\checkpoints\voice_spotify_2026-10-23\test_transcript_dedup.py`
- `C:\JARVIS\tmp\checkpoints\voice_spotify_2026-10-23\SpotifyLoopback\`

These are recovery snapshots only. The active implementation remains in the normal project files.

## Next physical test

1. Leave Spotify playing a spoken advertisement or voice-heavy track while remaining silent for at least 30–60 seconds: expected **zero user turns, zero replies, zero tools**.
2. While Spotify continues, speak a normal question: expected one complete user turn and normal response without pausing Spotify.
3. If either fails, keep the current 2500 ms VAD timing and work only on `shadow_v4`; do not disturb the now-good conversation timing or transcription assembly.
