from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


logger = logging.getLogger(__name__)

AudioKind = Literal["input", "output"]
DEFAULT_DEVICE_ID = "windows-default"
DEFAULT_SETTINGS_PATH = Path.home() / ".jarvis" / "config" / "audio_devices.json"


@dataclass(frozen=True)
class AudioDevice:
    device_id: str
    name: str
    display_name: str
    host_api: str
    index: int | None
    kind: AudioKind
    is_default: bool = False
    available: bool = True

    def to_ui_dict(self) -> dict[str, Any]:
        return asdict(self)


class AudioDeviceManager:
    """Stable, persisted device preferences over PortAudio's volatile indices."""

    def __init__(
        self,
        sounddevice_module,
        *,
        settings_path: Path | str = DEFAULT_SETTINGS_PATH,
        input_rate: int = 16000,
        output_rate: int = 24000,
        channels: int = 1,
    ) -> None:
        self._sd = sounddevice_module
        self.settings_path = Path(settings_path)
        self.input_rate = int(input_rate)
        self.output_rate = int(output_rate)
        self.channels = int(channels)
        self._lock = threading.RLock()
        self._preferences = {"input": DEFAULT_DEVICE_ID, "output": DEFAULT_DEVICE_ID}
        self._last_resolution: dict[str, tuple[str, bool] | None] = {
            "input": None,
            "output": None,
        }
        self._load()

    @staticmethod
    def _stable_id(kind: AudioKind, host_api: str, name: str, occurrence: int) -> str:
        identity = f"{kind}\0{host_api.casefold()}\0{name.casefold()}\0{occurrence}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        return f"{kind}-{digest}"

    def _load(self) -> None:
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
            return
        for kind in ("input", "output"):
            value = payload.get(kind)
            if isinstance(value, str) and value:
                self._preferences[kind] = value

    def _save(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix(self.settings_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._preferences, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.settings_path)

    def preferred_id(self, kind: AudioKind) -> str:
        return self._preferences[kind]

    def _host_api_name(self, device: dict[str, Any]) -> str:
        try:
            host_api = self._sd.query_hostapis(int(device.get("hostapi", -1)))
            return str(host_api.get("name") or "Windows audio")
        except Exception:
            return "Windows audio"

    def _wasapi_host_api_index(self) -> int | None:
        """Return the Windows WASAPI host API index when PortAudio exposes it."""
        try:
            host_apis = list(self._sd.query_hostapis())
        except Exception:
            return None
        for index, host_api in enumerate(host_apis):
            if "wasapi" in str(host_api.get("name") or "").casefold():
                return index
        return None

    def _default_index(self, kind: AudioKind) -> int | None:
        wasapi_index = self._wasapi_host_api_index()
        if wasapi_index is not None:
            try:
                host_api = self._sd.query_hostapis(wasapi_index)
                key = "default_input_device" if kind == "input" else "default_output_device"
                endpoint_index = int(host_api.get(key, -1))
                if endpoint_index >= 0:
                    endpoint = dict(self._sd.query_devices(endpoint_index))
                    endpoint_name = str(endpoint.get("name") or "").strip()
                    transport_index = self._transport_index_for_endpoint(
                        endpoint_name, kind, list(self._sd.query_devices())
                    )
                    if transport_index is not None:
                        return transport_index
            except Exception:
                pass

        slot = 0 if kind == "input" else 1
        try:
            value = self._sd.default.device
            index = value[slot] if isinstance(value, (tuple, list)) else value
            index = int(index)
            return index if index >= 0 else None
        except Exception:
            return None

    def _supports(self, index: int, kind: AudioKind) -> bool:
        try:
            checker = (
                self._sd.check_input_settings
                if kind == "input"
                else self._sd.check_output_settings
            )
            checker(
                device=index,
                samplerate=self.input_rate if kind == "input" else self.output_rate,
                channels=self.channels,
                dtype="int16",
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _device_names_match(endpoint_name: str, candidate_name: str) -> bool:
        endpoint = " ".join(str(endpoint_name or "").casefold().split())
        candidate = " ".join(str(candidate_name or "").casefold().split())
        if not endpoint or not candidate:
            return False
        if endpoint == candidate:
            return True
        # Legacy MME names are often truncated while DirectSound/WASAPI keep the full name.
        shorter, longer = sorted((endpoint, candidate), key=len)
        return len(shorter) >= 18 and longer.startswith(shorter)

    def _transport_index_for_endpoint(
        self,
        endpoint_name: str,
        kind: AudioKind,
        devices: list[dict[str, Any]],
    ) -> int | None:
        channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
        candidates: list[tuple[int, int]] = []
        for index, raw in enumerate(devices):
            device = dict(raw)
            if int(device.get(channel_key, 0) or 0) < self.channels:
                continue
            candidate_name = str(device.get("name") or "").strip()
            if not self._device_names_match(endpoint_name, candidate_name):
                continue
            host_name = self._host_api_name(device).casefold()
            if "mme" in host_name:
                priority = 0
            elif "directsound" in host_name:
                priority = 1
            elif "wasapi" in host_name:
                priority = 2
            else:
                priority = 9
            candidates.append((priority, index))
        for _, index in sorted(candidates):
            if self._supports(index, kind):
                return index
        return None

    def list_devices(self, kind: AudioKind) -> list[AudioDevice]:
        with self._lock:
            devices = list(self._sd.query_devices())
            default_index = self._default_index(kind)
            result = [AudioDevice(
                device_id=DEFAULT_DEVICE_ID,
                name="Dispositivo predeterminado de Windows",
                display_name="Dispositivo predeterminado de Windows",
                host_api="Windows",
                index=None,
                kind=kind,
                is_default=True,
            )]
            occurrences: dict[tuple[str, str], int] = {}
            channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
            wasapi_index = self._wasapi_host_api_index()
            for endpoint_index, raw in enumerate(devices):
                device = dict(raw)
                if int(device.get(channel_key, 0) or 0) < self.channels:
                    continue
                if wasapi_index is not None and int(device.get("hostapi", -1)) != wasapi_index:
                    continue
                name = str(device.get("name") or f"Audio device {endpoint_index}").strip()
                host_api = self._host_api_name(device)
                signature = (host_api.casefold(), name.casefold())
                occurrence = occurrences.get(signature, 0)
                occurrences[signature] = occurrence + 1
                display_name = name
                transport_index = (
                    self._transport_index_for_endpoint(name, kind, devices)
                    if wasapi_index is not None
                    else endpoint_index
                )
                available = transport_index is not None and self._supports(transport_index, kind)
                result.append(AudioDevice(
                    device_id=self._stable_id(kind, host_api, name, occurrence),
                    name=name,
                    display_name=display_name,
                    host_api=host_api,
                    index=transport_index if transport_index is not None else endpoint_index,
                    kind=kind,
                    is_default=transport_index == default_index,
                    available=available,
                ))
            return result

    def list_input_devices(self) -> list[AudioDevice]:
        return self.list_devices("input")

    def list_output_devices(self) -> list[AudioDevice]:
        return self.list_devices("output")

    def refresh_devices(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "inputs": [device.to_ui_dict() for device in self.list_input_devices()],
            "outputs": [device.to_ui_dict() for device in self.list_output_devices()],
            "selected_input": self.preferred_id("input"),
            "selected_output": self.preferred_id("output"),
        }

    def _select(self, kind: AudioKind, device_id: str) -> AudioDevice:
        with self._lock:
            selected = next(
                (item for item in self.list_devices(kind) if item.device_id == device_id),
                None,
            )
            if selected is None:
                raise ValueError(f"Unknown {kind} audio device: {device_id}")
            if selected.index is not None and not self._supports(selected.index, kind):
                raise ValueError(f"Audio device is incompatible with AURORA: {selected.name}")
            self._preferences[kind] = selected.device_id
            self._save()
            logger.info(
                "AUDIO_%s selected device_id=%s device_name=%s",
                kind.upper(), selected.device_id, selected.name,
            )
            return selected

    def select_input(self, device_id: str) -> AudioDevice:
        return self._select("input", device_id)

    def select_output(self, device_id: str) -> AudioDevice:
        return self._select("output", device_id)

    def _resolve(self, kind: AudioKind) -> tuple[int | None, str, bool]:
        with self._lock:
            devices = self.list_devices(kind)
            preferred_id = self._preferences[kind]
            preferred = next((item for item in devices if item.device_id == preferred_id), None)
            if preferred is not None:
                if preferred.index is None:
                    index = self._default_index(kind)
                    usable = index is not None and self._supports(index, kind)
                    if usable:
                        try:
                            name = str(self._sd.query_devices(index).get("name") or "Windows default")
                        except Exception:
                            name = "Windows default"
                    else:
                        name = preferred.name
                else:
                    index = preferred.index
                    name = preferred.name
                    usable = self._supports(index, kind)
                if usable:
                    resolution = (preferred.device_id, True)
                    previous = self._last_resolution[kind]
                    if previous is not None and previous[1] is False and preferred_id != DEFAULT_DEVICE_ID:
                        logger.info(
                            "AUDIO_DEVICE recovered type=%s device_id=%s device_name=%s",
                            kind, preferred.device_id, preferred.name,
                        )
                    self._last_resolution[kind] = resolution
                    return index, name, preferred_id != DEFAULT_DEVICE_ID

            default_index = self._default_index(kind)
            if default_index is None or not self._supports(default_index, kind):
                fallback = next(
                    (item for item in devices[1:] if item.index is not None and self._supports(item.index, kind)),
                    None,
                )
                if fallback is None:
                    raise RuntimeError(f"No compatible {kind} audio device is available")
                default_index, default_name = fallback.index, fallback.name
            else:
                try:
                    default_name = str(self._sd.query_devices(default_index).get("name") or "Windows default")
                except Exception:
                    default_name = "Windows default"
            previous = self._last_resolution[kind]
            resolution = (preferred_id, False)
            if previous != resolution:
                logger.warning(
                    "AUDIO_DEVICE fallback type=%s preferred_device_id=%s fallback_device_name=%s",
                    kind, preferred_id, default_name,
                )
            self._last_resolution[kind] = resolution
            return default_index, default_name, False

    def resolve_input(self) -> tuple[int | None, str]:
        index, name, _ = self._resolve("input")
        return index, name

    def resolve_output(self) -> tuple[int, str, bool]:
        index, name, preferred = self._resolve("output")
        if index is None:
            raise RuntimeError("No compatible output audio device is available")
        return index, name, preferred
