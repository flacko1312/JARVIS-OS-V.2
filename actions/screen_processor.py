from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from core.vision_model import (
    OllamaVisionConfig,
    configured_ollama_vision,
    configured_vision_fallback_model,
    configured_vision_model,
)
from memory.config_manager import get_gemini_key

import numpy as np
import httpx
import requests
import sounddevice as sd

def _get_voice_name() -> str:
    """Read voice name dynamically so it picks up runtime changes."""
    v = os.environ.get("GEMINI_VOICE_NAME", "").strip().lower()
    return v if v else "puck"

DEFAULT_VOICE_NAME = _get_voice_name()

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as gtypes

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE        = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config_key(key: str, value) -> None:
    try:
        cfg = _load_config()
        cfg[key] = value
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Vision] ⚠️  Could not save config key '{key}': {e}")


def _get_api_key() -> str:
    key = get_gemini_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set (set GEMINI_API_KEY env var).")
    return key


def _get_os() -> str:
    return _load_config().get("os_system", "windows").lower()

_LIVE_MODEL         = "models/gemini-2.5-flash-native-audio-preview-12-2025"
_CHANNELS           = 1
_RECEIVE_SAMPLE_RATE = 24_000
_CHUNK_SIZE         = 1_024

_IMG_MAX_W = 1600
_IMG_MAX_H = 1000
_JPEG_Q    = 82

_last_capture_time = 0.0
_MIN_CAPTURE_INTERVAL = 0.5  # seconds

_SYSTEM_PROMPT = (
    "El idioma de interacción del usuario es español. Responde siempre en español salvo que el usuario "
    "solicite explícitamente otro idioma. Eres AURORA, un asistente avanzado de IA. "
    "Analyze the provided image with precision and intelligence. "
    "Be concise and direct — maximum two sentences unless the user's question "
    "requires more detail. "
    "Address the user respectfully. "
    "Only state text, names, buttons, or UI details that are legible in the image. "
    "If something is unclear, say that it is unclear instead of guessing. "
    "Presenta el resultado final en español por defecto."
)


def _compress(img_bytes: bytes, source_format: str = "PNG") -> tuple[bytes, str]:
    if not _PIL:
        return img_bytes, f"image/{source_format.lower()}"

    try:
        img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[Vision] ⚠️  Image compress failed: {e}")
        return img_bytes, f"image/{source_format.lower()}"

def _capture_screen() -> tuple[bytes, str]:

    if not _MSS:
        raise RuntimeError("mss is not installed. Run: pip install mss")

    with mss.mss() as sct:
        monitors = sct.monitors          # [0] = all combined, [1..n] = real screens
        target   = monitors[1] if len(monitors) > 1 else monitors[0]
        shot     = sct.grab(target)
        png      = mss.tools.to_png(shot.rgb, shot.size)

    return _compress(png, "PNG")


def _cv2_backend() -> int:
    """Return the best OpenCV camera backend for the current OS."""
    if not _CV2:
        return 0
    os_name = _get_os()
    if os_name == "windows":
        return cv2.CAP_DSHOW    
    if os_name == "mac":
        return cv2.CAP_AVFOUNDATION  
    return cv2.CAP_ANY


def _probe_camera(index: int, backend: int, warmup: int = 2) -> bool:

    if not _CV2:
        return False
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return False
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    return bool(np.mean(frame) > 8)


def _detect_camera_index() -> int:

    backend = _cv2_backend()
    print("[Vision] 🔍 Auto-detecting camera...")
    for idx in range(6):
        if _probe_camera(idx, backend):
            print(f"[Vision] ✅ Camera found at index {idx}")
            _save_config_key("camera_index", idx)
            return idx
        print(f"[Vision] ⚠️  Camera index {idx}: no usable frame")

    print("[Vision] ⚠️  No camera found — defaulting to index 0")
    _save_config_key("camera_index", 0)
    return 0


def _get_camera_index() -> int:
    cfg = _load_config()
    if "camera_index" in cfg:
        return int(cfg["camera_index"])
    return _detect_camera_index()


def _capture_camera() -> tuple[bytes, str]:
    if not _CV2:
        raise RuntimeError("OpenCV (cv2) is not installed. Run: pip install opencv-python")

    index   = _get_camera_index()
    backend = _cv2_backend()
    cap     = cv2.VideoCapture(index, backend)

    if not cap.isOpened():
        raise RuntimeError(f"Camera index {index} could not be opened.")

    for _ in range(3):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("Camera returned no frame.")

    if _PIL:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q)
        return buf.getvalue(), "image/jpeg"

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])
    return buf.tobytes(), "image/jpeg"


def _vision_http_options() -> gtypes.HttpOptions:
    """Use the SDK retry loop once for overloaded vision models only."""
    return gtypes.HttpOptions(
        retry_options=gtypes.HttpRetryOptions(
            attempts=2,
            initial_delay=0.5,
            max_delay=1.0,
            exp_base=2,
            jitter=0.2,
            http_status_codes=[503],
        )
    )


def _vision_request_config() -> gtypes.GenerateContentConfig:
    return gtypes.GenerateContentConfig(
        # This request never exposes tools. Disabling SDK-side automatic
        # function calling preserves behavior and avoids its Models API warning.
        automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(
            disable=True
        )
    )


def _vision_error(code: int | None) -> RuntimeError:
    if code == 503:
        return RuntimeError(
            "Vision service unavailable (503) after bounded retries. "
            "Please try again later."
        )
    if code == 429:
        return RuntimeError(
            "Vision request was rate-limited or exceeded quota (429). "
            "No fallback was attempted."
        )
    if code in (401, 403):
        return RuntimeError(
            f"Vision authentication or authorization failed ({code}). "
            "No retry or fallback was attempted."
        )
    if code is not None and 400 <= code < 500:
        return RuntimeError(
            f"Vision model or request configuration failed ({code}). "
            "No retry or fallback was attempted."
        )
    if code is not None:
        return RuntimeError(f"Vision service failed with HTTP {code}.")
    return RuntimeError("Vision analysis failed before a valid response was returned.")


def _request_vision_answer(client, model: str, contents: list) -> str:
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=_vision_request_config(),
    )
    text = (getattr(response, "text", "") or "").strip()
    if not text:
        raise RuntimeError("Gemini returned no text for the screen image.")
    return re.sub(r"\s+", " ", text).strip()


def _provider_unavailable(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.APIError):
        return exc.code in {500, 502, 503, 504}
    return isinstance(exc, (httpx.RequestError, TimeoutError, ConnectionError))


def _request_ollama_vision_answer(
    config: OllamaVisionConfig,
    image_bytes: bytes,
    user_text: str,
) -> str:
    prompt = (
        "Analyze the supplied image and answer the user's question. "
        "Describe only what is actually visible. Only report text or details "
        "that are clearly legible, and explicitly say when something is unclear. "
        "Do not invent unreadable text, people, accounts, or UI state.\n\n"
        f"User question: {user_text}"
    )
    response = requests.post(
        f"{config.url}/api/chat",
        json={
            "model": config.model,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64.b64encode(image_bytes).decode("ascii")],
                }
            ],
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 512},
        },
        timeout=(config.connect_timeout, config.read_timeout),
    )
    if not response.ok:
        detail = ""
        try:
            detail = response.json().get("error", response.text[:200])
        except Exception:
            detail = response.text[:200] if response.text else ""
        raise RuntimeError(
            f"Ollama vision HTTP {response.status_code}: {detail}"
        )
    try:
        text = str(response.json().get("message", {}).get("content", "")).strip()
    except (TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError("Local Ollama vision returned an invalid response.") from exc
    if not text:
        raise RuntimeError("Local Ollama vision returned no visual answer.")
    return re.sub(r"\s+", " ", text).strip()


def _local_vision_answer(
    image_bytes: bytes,
    user_text: str,
    gemini_failure: Exception,
) -> str:
    try:
        config = configured_ollama_vision(_CONFIG_PATH)
    except ValueError as exc:
        raise RuntimeError(
            f"Gemini vision unavailable; local vision configuration failed: {exc}"
        ) from exc

    if not config.enabled:
        raise RuntimeError(
            "Gemini vision unavailable and local Ollama vision is disabled."
        ) from gemini_failure

    print(f"[Vision] Gemini providers unavailable; trying local Ollama: {config.model}")
    try:
        return _request_ollama_vision_answer(config, image_bytes, user_text)
    except (requests.RequestException, RuntimeError) as exc:
        raise RuntimeError(
            "Gemini vision unavailable and local Ollama vision failed: "
            f"{type(exc).__name__}."
        ) from exc


def _direct_vision_answer(image_bytes: bytes, mime_type: str, user_text: str) -> str:
    client = genai.Client(
        api_key=_get_api_key(),
        http_options=_vision_http_options(),
    )
    primary_model = configured_vision_model(_CONFIG_PATH)
    fallback_model = configured_vision_fallback_model(_CONFIG_PATH)
    prompt = (
        f"{_SYSTEM_PROMPT}\n\n"
        "For screen analysis, prioritize visible on-screen text and exact UI state. "
        "Do not identify people, recipients, or accounts unless the name is clearly readable. "
        "If multiple names are visible, distinguish the active chat/header from side-list names. "
        "Answer the user's question directly.\n\n"
        f"User question: {user_text}"
    )
    contents = [
        gtypes.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        prompt,
    ]

    print(f"[Vision] Primary model: {primary_model}")
    try:
        return _request_vision_answer(client, primary_model, contents)
    except genai_errors.APIError as exc:
        if exc.code != 503:
            if _provider_unavailable(exc):
                return _local_vision_answer(image_bytes, user_text, exc)
            raise _vision_error(exc.code) from exc

        if not fallback_model or fallback_model == primary_model:
            return _local_vision_answer(image_bytes, user_text, exc)

        print(
            "[Vision] Primary unavailable (503); "
            f"trying fallback: {fallback_model}"
        )
        try:
            return _request_vision_answer(client, fallback_model, contents)
        except genai_errors.APIError as fallback_exc:
            if _provider_unavailable(fallback_exc):
                return _local_vision_answer(
                    image_bytes, user_text, fallback_exc
                )
            raise _vision_error(fallback_exc.code) from fallback_exc
        except (httpx.RequestError, TimeoutError, ConnectionError) as fallback_exc:
            return _local_vision_answer(image_bytes, user_text, fallback_exc)
    except (httpx.RequestError, TimeoutError, ConnectionError) as exc:
        return _local_vision_answer(image_bytes, user_text, exc)

class _VisionSession:
    def __init__(self):
        self._loop:       Optional[asyncio.AbstractEventLoop] = None
        self._thread:     Optional[threading.Thread]          = None
        self._session                                          = None
        self._out_queue:  Optional[asyncio.Queue]             = None
        self._audio_in:   Optional[asyncio.Queue]             = None
        self._ready_evt:  threading.Event                     = threading.Event()
        self._player                                           = None
        self._lock:       threading.Lock                       = threading.Lock()
        self._result_fut:   Optional[asyncio.Future]          = None
        self._result_lock:  threading.Lock                       = threading.Lock()

    def start(self, player=None, timeout: float = 15.0) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                if player is not None:
                    self._player = player
                return
            self._player = player
            self._thread = threading.Thread(
                target=self._run_event_loop,
                daemon=True,
                name="VisionSessionThread",
            )
            self._thread.start()

        if not self._ready_evt.wait(timeout=timeout):
            raise RuntimeError(f"Vision session did not connect within {timeout}s.")
        print("[Vision] ✅ Session ready")

    def analyze(self, image_bytes: bytes, mime_type: str, user_text: str) -> None:
        if not self._loop or not self._out_queue:
            print("[Vision] ⚠️  Session not started — dropping request")
            return
        asyncio.run_coroutine_threadsafe(
            self._out_queue.put((image_bytes, mime_type, user_text)),
            self._loop,
        )

    def request(self, image_bytes: bytes, mime_type: str, user_text: str, timeout: float = 8.0) -> Optional[str]:
        if not self._loop or not self._out_queue:
            print("[Vision] ⚠️  Session not started — dropping request")
            return None
        # Create a future bound to the vision session's event loop
        async def _make_future():
            return asyncio.Future()
        fut = asyncio.run_coroutine_threadsafe(_make_future(), self._loop).result()
        with self._result_lock:
            self._result_fut = fut
        asyncio.run_coroutine_threadsafe(
            self._out_queue.put((image_bytes, mime_type, user_text)),
            self._loop,
        )
        # Wait for the future with a timeout using the vision loop
        async def _wait_with_timeout(f, t):
            return await asyncio.wait_for(f, t)
        wait_fut = asyncio.run_coroutine_threadsafe(_wait_with_timeout(fut, timeout), self._loop)
        try:
            return wait_fut.result()
        except asyncio.TimeoutError:
            print("[Vision] ⚠️  No response from model within timeout")
            return None
        except Exception as e:
            print(f"[Vision] ⚠️  Error waiting for vision result: {e}")
            return None
        finally:
            with self._result_lock:
                self._result_fut = None

    def is_ready(self) -> bool:
        return self._session is not None

    def _run_event_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._session_loop())

    async def _session_loop(self) -> None:
        self._out_queue = asyncio.Queue(maxsize=30)
        self._audio_in  = asyncio.Queue()

        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"},
        )

        backoff = 2.0
        while True:
            # Build config each reconnect to pick up voice changes
            voice = _get_voice_name()
            config = gtypes.LiveConnectConfig(
                response_modalities=["AUDIO"],
                output_audio_transcription={},
                system_instruction=_SYSTEM_PROMPT,
                speech_config=gtypes.SpeechConfig(
                    voice_config=gtypes.VoiceConfig(
                        prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(
                            voice_name=voice
                        )
                    )
                ),
            )
            try:
                print("[Vision] 🔌 Connecting...")
                async with client.aio.live.connect(
                    model=_LIVE_MODEL, config=config
                ) as session:
                    self._session = session
                    self._ready_evt.set()
                    backoff = 2.0  
                    print("[Vision] ✅ Connected")

                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._send_loop())
                        tg.create_task(self._recv_loop())
                        tg.create_task(self._play_loop())

            except* Exception as eg:
                for exc in eg.exceptions:
                    print(f"[Vision] ⚠️  Session error: {exc}")
            finally:
                self._session = None
                self._ready_evt.clear()

            print(f"[Vision] 🔄 Reconnecting in {backoff:.0f}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.3, 15.0)
            self._ready_evt.set()  

    async def _send_loop(self) -> None:
        while True:
            try:
                image_bytes, mime_type, user_text = await asyncio.wait_for(self._out_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if not self._session:
                print("[Vision] ⚠️  No session — dropping image")
                continue
            try:
                b64 = base64.b64encode(image_bytes).decode("ascii")
                await self._session.send_client_content(
                    turns={
                        "parts": [
                            {"inline_data": {"mime_type": mime_type, "data": b64}},
                            {"text": user_text},
                        ]
                    },
                    turn_complete=True,
                )
                print(f"[Vision] 📤 Sent {len(image_bytes):,} bytes — '{user_text[:60]}'")
            except Exception as e:
                print(f"[Vision] ⚠️  Send error: {e}")

    async def _recv_loop(self) -> None:
        transcript: list[str] = []
        while True:
            try:
                async for response in self._session.receive():
                    if response.data:
                        await self._audio_in.put(response.data)

                    sc = response.server_content
                    if not sc:
                        continue

                    if sc.output_transcription and sc.output_transcription.text:
                        chunk = sc.output_transcription.text.strip()
                        if chunk:
                            transcript.append(chunk)

                    if sc.turn_complete:
                        result_text = ""
                        if transcript:
                            result_text = re.sub(r"\s+", " ", " ".join(transcript)).strip()
                        if result_text and self._player:
                            self._player.write_log(f"Jarvis: {result_text}")
                            print(f"[Vision] 💬 {result_text}")
                        # Set result for the pending request
                        with self._result_lock:
                            if self._result_fut and not self._result_fut.done():
                                self._result_fut.set_result(result_text)
                        transcript = []

                # Iterator exhausted — session closed by server, raise to trigger reconnect
                print("[Vision] ⚠️  Receive stream ended — will reconnect")
                raise RuntimeError("Receive stream ended")

            except Exception as e:
                print(f"[Vision] ⚠️  Recv error: {e}")
                raise

    async def _play_loop(self) -> None:
        stream = sd.RawOutputStream(
            samplerate=_RECEIVE_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype="int16",
            blocksize=_CHUNK_SIZE,
        )
        stream.start()
        try:
            while True:
                chunk = await self._audio_in.get()
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[Vision] ❌ Play error: {e}")
            raise
        finally:
            stream.stop()
            stream.close()

_session      = _VisionSession()
_session_lock = threading.Lock()
_session_up   = False


def _ensure_session(player=None) -> None:
    global _session_up
    with _session_lock:
        if not _session_up or not _session.is_ready():
            # Reset and start fresh if session died
            _session_up = False
            _session.start(player=player)
            _session_up = True
        elif player is not None:
            _session._player = player


def screen_process(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    global _last_capture_time
    preview_active = False

    def _deliver(message: str, *, error: bool = False) -> str:
        """Route the vision result to speech, with the log as a fallback."""
        spoken = False
        if callable(speak):
            try:
                spoken = bool(speak(message))
            except Exception as exc:
                print(f"[Vision] ⚠️  Speech handoff failed: {exc}")
        if player and not spoken:
            try:
                prefix = "ERR" if error else "Jarvis"
                player.write_log(f"{prefix}: {message}")
            except Exception:
                pass
        if preview_active and player and hasattr(player, "hide_vision_preview"):
            try:
                # Keep the live feed visible while the spoken result is likely
                # still playing, then release its camera/screen resources.
                hold_ms = 2400 if error else max(2200, min(10_000, len(message) * 55))
                player.hide_vision_preview(hold_ms)
            except Exception:
                pass
        return message

    params    = parameters or {}
    user_text = (params.get("text") or params.get("user_text") or "").strip()
    angle     = params.get("angle", "screen").lower().strip()

    if not user_text:
        print("[Vision] ⚠️  No question provided — aborting")
        return _deliver("No vision question was provided.", error=True)

    print(f"[Vision] ▶ angle={angle!r}  question='{user_text[:80]}'")

    # Cooldown to prevent excessive captures
    now = time.time()
    if now - _last_capture_time < _MIN_CAPTURE_INTERVAL:
        print(f"[Vision] ⚠️  Capture too frequent — skipping")
        return _deliver("Screen capture skipped because requests are too frequent.", error=True)

    try:
        if angle == "camera":
            image_bytes, mime_type = _capture_camera()
            print(f"[Vision] 📷 Camera: {len(image_bytes):,} bytes")
        else:
            image_bytes, mime_type = _capture_screen()
            print(f"[Vision] 🖥️  Screen: {len(image_bytes):,} bytes")
        _last_capture_time = now
    except Exception as e:
        print(f"[Vision] ❌ Capture error: {e}")
        return _deliver(f"Screen capture failed: {e}", error=True)

    if player and hasattr(player, "show_vision_preview"):
        try:
            player.show_vision_preview(angle)
            preview_active = True
        except Exception as exc:
            print(f"[Vision] ⚠️  Live preview unavailable: {exc}")

    try:
        result = _direct_vision_answer(image_bytes, mime_type, user_text)
    except Exception as e:
        print(f"[Vision] ❌ Analysis error: {e}")
        return _deliver(f"Screen analysis failed: {e}", error=True)

    print(f"[Vision] 💬 {result}")
    return _deliver(result)


def warmup_session(player=None) -> None:
    try:
        _ensure_session(player=player)
    except Exception as e:
        print(f"[Vision] ⚠️  Warmup failed: {e}")

if __name__ == "__main__":
    print("[TEST] screen_processor.py")
    print("=" * 52)
    mode = input("angle — screen / camera (default: screen): ").strip().lower() or "screen"
    q    = input("Question (Enter = default): ").strip() or "What do you see? Be brief."

    t0 = time.perf_counter()
    warmup_session()
    print(f"Session ready in {time.perf_counter()-t0:.2f}s\n")

    t1 = time.perf_counter()
    ok = screen_process({"angle": mode, "text": q})
    print(f"Queued in {time.perf_counter()-t1:.3f}s — waiting for audio...")
    time.sleep(10)
    print("Done." if ok else "Failed.")
