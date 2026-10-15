"""Cross-platform music and media playback control, with Spotify first-class support."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from urllib.parse import quote, urlparse


_SYSTEM = platform.system()

_ACTION_ALIASES = {
    "resume": "play",
    "continue": "play",
    "play_pause": "toggle",
    "playpause": "toggle",
    "toggle_playback": "toggle",
    "skip": "next",
    "next_track": "next",
    "prev": "previous",
    "previous_track": "previous",
    "volume_up": "volume_up",
    "volume_down": "volume_down",
    "set_volume": "set_volume",
}

_PLATFORM_ALIASES = {
    "": "spotify",
    "music": "spotify",
    "spotify app": "spotify",
    "apple": "apple_music",
    "apple music": "apple_music",
    "itunes": "apple_music",
    "youtube": "youtube_music",
    "youtube music": "youtube_music",
    "yt music": "youtube_music",
    "default": "system",
}


def _run(command: list[str], timeout: int = 12) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _run_osascript(script: str, *arguments: str) -> subprocess.CompletedProcess:
    return _run(["osascript", "-e", script, *arguments])


def _open_uri(uri: str) -> tuple[bool, str]:
    try:
        if _SYSTEM == "Windows":
            os.startfile(uri)  # type: ignore[attr-defined]
            return True, ""
        command = ["open", uri] if _SYSTEM == "Darwin" else ["xdg-open", uri]
        result = _run(command)
        if result.returncode == 0:
            return True, ""
        return False, (result.stderr or result.stdout or "request rejected").strip()
    except Exception as exc:
        return False, str(exc)


def _spotify_uri(value: str) -> str:
    """Convert Spotify links to app URIs; return an empty string for plain search text."""
    value = str(value or "").strip()
    if value.lower().startswith("spotify:"):
        return value
    try:
        parsed = urlparse(value)
        if parsed.netloc.lower() not in {"open.spotify.com", "play.spotify.com"}:
            return ""
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"track", "album", "playlist", "artist", "episode", "show"}:
            return f"spotify:{parts[0]}:{parts[1]}"
    except Exception:
        pass
    return ""


def _spotify_macos(action: str, query: str) -> str:
    if action == "play_query":
        uri = _spotify_uri(query)
        if uri:
            script = (
                'on run argv\n'
                'tell application "Spotify"\n'
                'activate\n'
                'play track (item 1 of argv)\n'
                'end tell\n'
                'end run'
            )
            result = _run_osascript(script, uri)
            if result.returncode == 0:
                return "Playing the requested item on Spotify."
            return f"Spotify could not play that link: {(result.stderr or result.stdout).strip()}"

        ok, detail = _open_uri(f"spotify:search:{quote(query)}")
        if ok:
            return f"Opened Spotify results for {query}. Select a result to begin playback."
        return f"Could not open Spotify search: {detail}"

    scripts = {
        "play": 'tell application "Spotify" to play',
        "pause": 'tell application "Spotify" to pause',
        "stop": (
            'tell application "Spotify"\n'
            'pause\n'
            'try\nset player position to 0\nend try\n'
            'end tell'
        ),
        "toggle": (
            'tell application "Spotify"\n'
            'if player state is playing then\n'
            'pause\nelse\nplay\nend if\n'
            'end tell'
        ),
        "next": 'tell application "Spotify" to next track',
        "previous": 'tell application "Spotify" to previous track',
    }
    result = _run_osascript(scripts[action])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Spotify did not respond").strip()
        return f"Spotify control failed: {detail}"
    labels = {
        "play": "Playing Spotify.",
        "pause": "Spotify paused.",
        "stop": "Spotify stopped.",
        "toggle": "Spotify playback toggled.",
        "next": "Skipped to the next Spotify track.",
        "previous": "Returned to the previous Spotify track.",
    }
    return labels[action]


def _apple_music_macos(action: str, query: str) -> str:
    if action == "play_query":
        script = (
            'on run argv\n'
            'set searchText to item 1 of argv\n'
            'tell application "Music"\n'
            'activate\n'
            'set matches to every file track of library playlist 1 whose name contains searchText\n'
            'if (count of matches) is 0 then return "NOT_FOUND"\n'
            'play item 1 of matches\n'
            'end tell\n'
            'return "PLAYING"\n'
            'end run'
        )
        result = _run_osascript(script, query)
        if result.returncode == 0 and "PLAYING" in result.stdout:
            return f"Playing {query} in Apple Music."
        if result.returncode == 0:
            return f"I could not find {query} in your Apple Music library."
        return f"Apple Music search failed: {(result.stderr or result.stdout).strip()}"

    command = {
        "toggle": "playpause",
        "next": "next track",
        "previous": "previous track",
    }.get(action, action)
    script = f'tell application "Music" to {command}'
    result = _run_osascript(script)
    if result.returncode != 0:
        return f"Apple Music control failed: {(result.stderr or result.stdout).strip()}"
    return f"Apple Music: {action} completed."


def _linux_playerctl(action: str, platform_name: str) -> str:
    if not shutil.which("playerctl"):
        return "Media control requires playerctl on Linux, but it is not installed."
    command = "play-pause" if action == "toggle" else action
    args = ["playerctl"]
    if platform_name == "spotify":
        args.extend(["--player", "spotify"])
    args.append(command)
    result = _run(args)
    if result.returncode != 0:
        return f"Media control failed: {(result.stderr or result.stdout or 'no active player').strip()}"
    return f"Media {action} completed."


def _generic_media_key(action: str) -> str:
    key_map = {
        "play": "playpause",
        "pause": "playpause",
        "toggle": "playpause",
        "stop": "stop",
        "next": "nexttrack",
        "previous": "prevtrack",
    }
    try:
        import pyautogui

        pyautogui.press(key_map[action])
        return f"System media {action} command sent."
    except Exception as exc:
        return f"System media control is unavailable: {exc}"


def _volume_percent(value: object) -> int:
    try:
        number = int(float(str(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError("Volume percentage must be a number from 0 to 100.") from exc
    if not 0 <= number <= 100:
        raise ValueError("Volume percentage must be between 0 and 100.")
    return number


def _windows_volume(action: str, level: int | None = None) -> str:
    try:
        from pycaw.pycaw import AudioUtilities

        endpoint = AudioUtilities.GetSpeakers().EndpointVolume
        if action == "set_volume":
            assert level is not None
            endpoint.SetMasterVolumeLevelScalar(level / 100.0, None)
            return f"System volume set to {level}%."
        if action in {"mute", "unmute", "toggle_mute"}:
            current = bool(endpoint.GetMute())
            desired = (not current) if action == "toggle_mute" else action == "mute"
            endpoint.SetMute(desired, None)
            return "System audio muted." if desired else "System audio unmuted."
    except (ImportError, AttributeError, OSError) as exc:
        return f"Exact Windows volume control is unavailable: {exc}"
    return _generic_volume_key(action)


def _generic_volume_key(action: str) -> str:
    key = {"volume_up": "volumeup", "volume_down": "volumedown", "toggle_mute": "volumemute"}.get(action)
    if not key:
        return f"System volume action '{action}' is unsupported on this platform."
    try:
        import pyautogui

        pyautogui.press(key)
        return f"System {action.replace('_', ' ')} command sent."
    except Exception as exc:
        return f"System volume control is unavailable: {exc}"


def _system_volume(action: str, level: int | None = None) -> str:
    if _SYSTEM == "Windows":
        if action in {"volume_up", "volume_down"}:
            return _generic_volume_key(action)
        return _windows_volume(action, level)
    if _SYSTEM == "Darwin":
        if action == "set_volume":
            command = f"set volume output volume {level}"
        elif action == "mute":
            command = "set volume with output muted"
        elif action == "unmute":
            command = "set volume without output muted"
        elif action == "toggle_mute":
            command = "set volume output muted not (output muted of (get volume settings))"
        else:
            return _generic_volume_key(action)
        result = _run_osascript(command)
        return (f"System {action.replace('_', ' ')} completed." if result.returncode == 0 else
                f"System volume control failed: {(result.stderr or result.stdout).strip()}")
    if _SYSTEM == "Linux":
        if shutil.which("pactl"):
            command = {
                "volume_up": ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"],
                "volume_down": ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"],
                "set_volume": ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
                "mute": ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"],
                "unmute": ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"],
                "toggle_mute": ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
            }[action]
            result = _run(command)
            return (f"System {action.replace('_', ' ')} completed." if result.returncode == 0 else
                    f"System volume control failed: {(result.stderr or result.stdout).strip()}")
        return _generic_volume_key(action)
    return _generic_volume_key(action)


def media_control(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    """Control Spotify, Apple Music, YouTube Music, or the active system player."""
    params = parameters or {}
    action = str(params.get("action", "toggle")).lower().strip().replace("-", "_").replace(" ", "_")
    action = _ACTION_ALIASES.get(action, action)
    platform_name = str(params.get("platform", "spotify")).lower().strip().replace("-", "_")
    platform_name = _PLATFORM_ALIASES.get(platform_name.replace("_", " "), platform_name)
    query = str(params.get("query", "")).strip()

    if action in {"queue", "inspect_queue", "list_queue"}:
        return (
            "Queue control is unsupported by the current provider architecture. "
            "JARVIS will not guess using provider-specific UI automation."
        )
    if action in {"volume_up", "volume_down", "mute", "unmute", "toggle_mute", "set_volume"}:
        try:
            level = _volume_percent(params.get("volume")) if action == "set_volume" else None
        except ValueError as exc:
            return str(exc)
        return _system_volume(action, level)

    if action == "play" and query:
        action = "play_query"
    allowed = {"play", "pause", "stop", "toggle", "next", "previous", "play_query"}
    if action not in allowed:
        return f"Unknown media action: '{action}'. Available: play, pause, stop, toggle, next, previous, play_query, volume_up, volume_down, set_volume, mute, unmute, toggle_mute."
    if platform_name not in {"spotify", "apple_music", "youtube_music", "system"}:
        return f"Unknown music platform: '{platform_name}'. Available: Spotify, Apple Music, YouTube Music, or system."
    if action == "play_query" and not query:
        return "Tell me which song, artist, album, playlist, or Spotify link to play."

    if player:
        player.write_log(f"[Media] {platform_name} // {action}" + (f" // {query}" if query else ""))

    if platform_name == "youtube_music" and action == "play_query":
        from actions.youtube_video import youtube_video

        return youtube_video({"action": "play", "query": query}, player=player)

    if action == "play_query" and platform_name not in {"spotify", "apple_music", "youtube_music"}:
        return "Choose Spotify, Apple Music, or YouTube Music when asking me to find a specific song."

    if platform_name == "spotify" and action == "play_query" and _SYSTEM != "Darwin":
        uri = _spotify_uri(query)
        ok, detail = _open_uri(uri or f"spotify:search:{quote(query)}")
        if ok:
            if uri:
                return "Opened the requested item in Spotify."
            return f"Opened Spotify results for {query}. Select a result to begin playback."
        return f"Could not open Spotify: {detail}"

    if _SYSTEM == "Darwin" and platform_name == "spotify":
        return _spotify_macos(action, query)
    if _SYSTEM == "Darwin" and platform_name == "apple_music":
        return _apple_music_macos(action, query)
    if _SYSTEM == "Linux":
        return _linux_playerctl(action, platform_name)
    return _generic_media_key(action)
