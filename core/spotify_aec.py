"""Spotify-aware microphone gate for Windows.

Spotify's rendered PCM is captured through Windows per-process loopback and used
only as a *reference*. WebRTC AEC3 analyses a copy of the microphone signal to
decide whether there is independent near-end speech. Gemini always receives the
original microphone PCM when user speech is present, so AEC cannot distort the
transcription. When Spotify is the only detected source, microphone frames are
withheld from Gemini.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
import psutil

logger = logging.getLogger("jarvis.spotify_aec")

try:
    from pywebrtc_audio import EchoCanceller, VoiceDetector
except ImportError:  # pragma: no cover
    EchoCanceller = None
    VoiceDetector = None


class SpotifyProcessAEC:
    """Use AEC3 as a shadow analyser; never feed AEC-processed speech to Gemini."""

    def __init__(self, sample_rate: int = 16000, *, helper_path: str | Path | None = None) -> None:
        self.sample_rate = int(sample_rate)
        root = Path(__file__).resolve().parents[1]
        self.helper_path = Path(
            helper_path or root / "tools" / "SpotifyLoopback" / "publish" / "SpotifyLoopback.exe"
        )
        legacy_enabled = (
            os.environ.get("JARVIS_SPOTIFY_AEC", "1").strip().lower()
            not in {"0", "false", "no", "off"}
        )
        requested_mode = os.environ.get("JARVIS_SPOTIFY_FILTER_MODE", "").strip().lower()
        self.mode = requested_mode or ("shadow_v1" if legacy_enabled else "off")
        if self.mode not in {"off", "shadow_v1", "shadow_v2", "shadow_v3", "shadow_v4"}:
            logger.warning("SPOTIFY_AEC invalid_mode=%r fallback=off", self.mode)
            self.mode = "off"
        self.enabled = (
            self.mode != "off"
            and sys.platform == "win32"
            and EchoCanceller is not None
            and VoiceDetector is not None
            and self.helper_path.exists()
            and not os.environ.get("PYTEST_CURRENT_TEST")
        )
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._last_reference_at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None
        self._aec = EchoCanceller(sample_rate=self.sample_rate, num_channels=1, stream_delay_ms=0) if self.enabled else None
        self._vad = VoiceDetector(sample_rate=self.sample_rate, num_channels=1) if self.enabled else None
        self._warned = False
        self._current_pid: int | None = None

        # Two 64-ms JARVIS chunks must agree before opening the raw mic path.
        # This eliminated all false near-speech detections in the recorded Spotify-only probe.
        self._near_candidate_chunks = 0
        self._near_speech_until = 0.0
        self._pause_guard_until = 0.0
        self._pause_guard_seconds = max(
            0.0,
            float(os.environ.get("JARVIS_SPOTIFY_PAUSE_GUARD_MS", "350")) / 1000.0,
        )
        self._preroll: deque[bytes] = deque(maxlen=4)  # ~256 ms at 16 kHz / 1024-sample chunks
        self._align_max_ms = max(20, int(os.environ.get("JARVIS_SPOTIFY_ALIGN_MAX_MS", "160")))
        self._align_step_ms = max(5, int(os.environ.get("JARVIS_SPOTIFY_ALIGN_STEP_MS", "10")))
        self._last_alignment_corr = 0.0
        self._last_alignment_lag_ms = 0.0
        self._last_metrics: dict[str, float] = {}

    @staticmethod
    def _spotify_root_pid() -> int | None:
        procs: dict[int, int] = {}
        for proc in psutil.process_iter(["pid", "ppid", "name"]):
            try:
                if str(proc.info.get("name") or "").casefold() == "spotify.exe":
                    procs[int(proc.info["pid"])] = int(proc.info.get("ppid") or 0)
            except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, TypeError, ValueError):
                continue
        roots = [pid for pid, ppid in procs.items() if ppid not in procs]
        return min(roots) if roots else (min(procs) if procs else None)

    @property
    def active(self) -> bool:
        return bool(self.enabled and self._thread and self._thread.is_alive())

    @property
    def metrics(self) -> dict[str, float]:
        return dict(self._last_metrics)

    def start(self) -> None:
        if not self.enabled or self.active:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._supervise, name="spotify-aec", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        with self._lock:
            self._buffer.clear()
            self._last_reference_at = 0.0
        self._reset_gate()

    def _reset_gate(self) -> None:
        self._near_candidate_chunks = 0
        self._near_speech_until = 0.0
        self._pause_guard_until = 0.0
        self._last_alignment_corr = 0.0
        self._last_alignment_lag_ms = 0.0
        self._preroll.clear()
        self._last_metrics = {}
        if self._aec is not None:
            self._aec.reset()
        if self._vad is not None:
            self._vad.reset()

    def _supervise(self) -> None:
        while not self._stop.is_set():
            pid = self._spotify_root_pid()
            if pid is None:
                self._current_pid = None
                self._stop.wait(0.5)
                continue
            try:
                self._capture_pid(pid)
            except Exception as exc:  # fail-open; never affect mic capture
                if not self._warned:
                    logger.warning("SPOTIFY_AEC helper_error=%s detail=%s", type(exc).__name__, exc)
                    self._warned = True
                self._stop.wait(0.5)

    def _capture_pid(self, pid: int) -> None:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            [str(self.helper_path), str(pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            bufsize=0,
            creationflags=creationflags,
        )
        self._proc = proc
        self._current_pid = pid
        self._warned = False
        logger.info("SPOTIFY_AEC reference_started pid=%d mode=%s", pid, self.mode)
        try:
            while not self._stop.is_set():
                chunk = proc.stdout.read(4096) if proc.stdout is not None else b""
                if not chunk:
                    break
                now = time.monotonic()
                with self._lock:
                    self._buffer.extend(chunk)
                    max_bytes = self.sample_rate * 2 * 2
                    if len(self._buffer) > max_bytes:
                        del self._buffer[: len(self._buffer) - max_bytes]
                    self._last_reference_at = now
        finally:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass
            self._proc = None
            with self._lock:
                self._buffer.clear()
                self._last_reference_at = 0.0
            self._reset_gate()
            logger.info("SPOTIFY_AEC reference_stopped pid=%d", pid)

    def _take_reference(self, needed: int, now: float) -> bytes | None:
        with self._lock:
            if now - self._last_reference_at > 0.25 or len(self._buffer) < needed:
                return None
            # Keep the reference close to realtime instead of allowing queue latency.
            if len(self._buffer) > needed * 3:
                del self._buffer[: len(self._buffer) - needed * 2]
            far = bytes(self._buffer[:needed])
            del self._buffer[:needed]
            return far

    def _take_aligned_reference(
        self, near_array: np.ndarray, now: float
    ) -> tuple[np.ndarray, float, float] | None:
        """Find the recent Spotify block that best matches the acoustic mic block."""
        needed_samples = int(near_array.size)
        max_lag_samples = int(self.sample_rate * self._align_max_ms / 1000.0)
        with self._lock:
            if now - self._last_reference_at > 0.25:
                return None
            snapshot = bytes(self._buffer)
        history = np.frombuffer(snapshot, dtype=np.int16)
        if needed_samples <= 0 or history.size < needed_samples + 1:
            return None
        max_lag_samples = min(max_lag_samples, int(history.size - needed_samples))
        step_samples = max(1, int(self.sample_rate * self._align_step_ms / 1000.0))
        near_float = near_array.astype(np.float64)
        near_float -= float(np.mean(near_float))
        near_norm = float(np.linalg.norm(near_float))
        if near_norm <= 1e-9:
            return None
        best_corr = -1.0
        best_lag = 0
        best_far = None
        for lag in range(0, max_lag_samples + 1, step_samples):
            end = int(history.size - lag)
            start = end - needed_samples
            if start < 0:
                break
            far = history[start:end]
            far_float = far.astype(np.float64)
            far_float -= float(np.mean(far_float))
            denom = near_norm * float(np.linalg.norm(far_float))
            corr = abs(float(np.dot(near_float, far_float) / denom)) if denom > 1e-9 else 0.0
            if corr > best_corr:
                best_corr = corr
                best_lag = lag
                best_far = far.copy()
        if best_far is None:
            return None
        lag_ms = best_lag * 1000.0 / self.sample_rate
        return best_far, best_corr, lag_ms

    def _suppressed_frames(self, pcm: bytes, now: float) -> tuple[bytes, ...]:
        """Represent blocked Spotify audio while preserving natural in-turn pauses."""
        if self.mode in {"shadow_v3", "shadow_v4"} and now < self._pause_guard_until:
            return ()
        if self.mode in {"shadow_v2", "shadow_v3", "shadow_v4"}:
            return (bytes(len(pcm)),)
        return ()

    def filter_input(self, pcm: bytes) -> tuple[bytes, ...]:
        """Gate Spotify leakage while always preserving original user PCM.

        ``shadow_v1`` keeps the previous experimental behavior for rollback/debug.
        ``shadow_v2`` sends realtime silence while Spotify is suppressed.
        ``shadow_v3`` preserves a short packet gap after user speech so a natural
        pause inside one sentence does not immediately become end-of-turn silence.
        """
        if not self.enabled or self._aec is None or self._vad is None or not pcm:
            return (pcm,) if pcm else ()

        now = time.monotonic()
        near_array = np.frombuffer(pcm, dtype=np.int16)
        alignment_corr = 0.0
        alignment_lag_ms = 0.0
        if self.mode == "shadow_v4":
            aligned = self._take_aligned_reference(near_array, now)
            if aligned is None:
                self._reset_gate()
                return (pcm,)
            far_array, alignment_corr, alignment_lag_ms = aligned
            self._last_alignment_corr = alignment_corr
            self._last_alignment_lag_ms = alignment_lag_ms
        else:
            far = self._take_reference(len(pcm), now)
            if far is None:
                self._reset_gate()
                return (pcm,)
            far_array = np.frombuffer(far, dtype=np.int16)
        if far_array.size == 0 or near_array.size != far_array.size:
            self._reset_gate()
            return (pcm,)

        far_rms = float(np.sqrt(np.mean(far_array.astype(np.float64) ** 2)))
        near_rms = float(np.sqrt(np.mean(near_array.astype(np.float64) ** 2)))
        if far_rms < 16.0:
            self._reset_gate()
            return (pcm,)

        was_open = now < self._near_speech_until
        if not was_open:
            self._preroll.append(bytes(pcm))

        try:
            cleaned = np.asarray(self._aec.process(near_array, far_array), dtype=np.int16)
            clean_rms = float(np.sqrt(np.mean(cleaned.astype(np.float64) ** 2)))
            voice_probability = float(self._vad.process(cleaned))
            residual_ratio = clean_rms / max(far_rms, 1.0)
            retention_ratio = clean_rms / max(near_rms, 1.0)

            if self.mode == "shadow_v1":
                candidate = (
                    clean_rms >= 300.0
                    and residual_ratio >= 0.25
                    and voice_probability >= 0.70
                )
                required_chunks = 2
                hangover_seconds = 0.34
            elif self.mode == "shadow_v4":
                # Correlation is measured against the digitally captured Spotify block.
                # Pure Spotify (including spoken ads) remains correlated after room pickup;
                # genuine near-end speech adds independent energy and breaks that match.
                independent_audio = alignment_corr < 0.40 or residual_ratio >= 1.50
                candidate = (
                    clean_rms >= 320.0
                    and voice_probability >= 0.78
                    and retention_ratio >= 0.55
                    and independent_audio
                )
                required_chunks = 3
                hangover_seconds = 0.20
            else:
                # Double-talk test used by shadow_v2/v3.
                candidate = (
                    clean_rms >= 320.0
                    and voice_probability >= 0.78
                    and retention_ratio >= 0.55
                    and (residual_ratio >= 0.55 or retention_ratio >= 0.72)
                )
                required_chunks = 3
                hangover_seconds = 0.20

            self._near_candidate_chunks = self._near_candidate_chunks + 1 if candidate else 0
            if self._near_candidate_chunks >= required_chunks:
                self._near_speech_until = now + hangover_seconds
                if self.mode in {"shadow_v3", "shadow_v4"}:
                    self._pause_guard_until = self._near_speech_until + self._pause_guard_seconds

            self._last_metrics = {
                "far_rms": far_rms,
                "near_rms": near_rms,
                "clean_rms": clean_rms,
                "residual_ratio": residual_ratio,
                "retention_ratio": retention_ratio,
                "voice_probability": voice_probability,
                "alignment_corr": alignment_corr,
                "alignment_lag_ms": alignment_lag_ms,
                "candidate_chunks": float(self._near_candidate_chunks),
                "gate_open": 1.0 if now < self._near_speech_until else 0.0,
            }
        except Exception as exc:
            if not self._warned:
                logger.warning("SPOTIFY_AEC analyse_error=%s detail=%s", type(exc).__name__, exc)
                self._warned = True
            self._reset_gate()
            return (pcm,)

        gate_open = now < self._near_speech_until
        if gate_open:
            if not was_open:
                frames = tuple(self._preroll)
                self._preroll.clear()
                logger.info(
                    "SPOTIFY_AEC near_speech_open mode=%s clean_rms=%.1f near_rms=%.1f far_rms=%.1f "
                    "far_ratio=%.3f retention=%.3f vad=%.3f corr=%.3f lag_ms=%.1f preroll=%d",
                    self.mode, clean_rms, near_rms, far_rms, residual_ratio,
                    retention_ratio, voice_probability, alignment_corr, alignment_lag_ms, len(frames),
                )
                return frames
            return (pcm,)

        return self._suppressed_frames(pcm, now)

    # Compatibility helper for focused tests/tools. It deliberately returns original
    # PCM only when the shadow gate decides it should be forwarded.
    def process(self, pcm: bytes) -> bytes:
        return b"".join(self.filter_input(pcm))
