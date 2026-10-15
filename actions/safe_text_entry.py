import json
import ctypes
import platform as platform_module
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ctypes import wintypes

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False


VISIBLE_TYPING_INTERVAL_SECONDS = 0.002
TEXT_ROLES = {"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"}
BROWSER_APPS = {"Google Chrome", "Brave Browser", "Microsoft Edge", "Arc", "Safari"}
MESSAGING_APPS = {"Messages", "WhatsApp", "Telegram", "Discord", "Signal", "Messenger"}
SAFE_POINTER_MESSAGE_APPS = BROWSER_APPS | MESSAGING_APPS
UNSAFE_TYPING_APPS = {
    "Terminal",
    "iTerm2",
    "Visual Studio Code",
    "Code",
}
MESSAGING_URL_MARKERS = (
    "instagram.com/direct",
    "messenger.com",
    "web.whatsapp.com",
    "web.telegram.org",
    "discord.com/channels",
)
MESSAGE_LABEL_MARKERS = (
    "message",
    "reply",
    "chat",
    "imessage",
    "send",
)
ADDRESS_LABEL_MARKERS = (
    "address",
    "url",
    "location",
    "omnibox",
)


@dataclass
class SafeTextEntryResult:
    ok: bool
    message: str
    target: str = ""
    click_before_typing: bool = False
    safety_path: str = ""
    target_id: tuple = ()
    readback_supported: bool = False


def _require_pyautogui() -> None:
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _actual_os() -> str:
    return {
        "Darwin": "mac",
        "Windows": "windows",
        "Linux": "linux",
    }.get(platform_module.system(), "unknown")


WINDOWS_EDIT_CONTROL_TYPE = 50004
WINDOWS_DOCUMENT_CONTROL_TYPE = 50030
WINDOWS_BLOCKED_PROCESSES = {
    "cmd.exe",
    "code.exe",
    "conhost.exe",
    "powershell.exe",
    "pwsh.exe",
    "windowsterminal.exe",
}
WINDOWS_DESKTOP_CLASSES = {"progman", "workerw", "syslistview32"}


def _windows_process_name(process_id: int) -> str:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, int(process_id))
    if not handle:
        return ""
    try:
        capacity = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(capacity)):
            return ""
        return Path(buffer.value).name
    finally:
        kernel32.CloseHandle(handle)


def _windows_focused_element_info() -> dict:
    """Describe the actual focused UIA element without changing focus."""
    if _actual_os() != "windows":
        return {}
    comtypes_module = None
    com_initialized = False
    try:
        import comtypes
        from comtypes.client import CreateObject
        from comtypes.gen import UIAutomationClient as UIA

        comtypes_module = comtypes
        comtypes.CoInitialize()
        com_initialized = True
        automation = CreateObject("UIAutomationClient.CUIAutomation")
        element = automation.GetFocusedElement()
        if element is None:
            return {}

        process_id = int(element.CurrentProcessId or 0)
        native_handle = int(element.CurrentNativeWindowHandle or 0)
        runtime_id = tuple(int(value) for value in (element.GetRuntimeId() or ()))
        info = {
            "process_id": process_id,
            "process_name": _windows_process_name(process_id),
            "control_type": int(element.CurrentControlType or 0),
            "class_name": str(element.CurrentClassName or ""),
            "name": str(element.CurrentName or ""),
            "automation_id": str(element.CurrentAutomationId or ""),
            "enabled": bool(element.CurrentIsEnabled),
            "keyboard_focusable": bool(element.CurrentIsKeyboardFocusable),
            "has_keyboard_focus": bool(element.CurrentHasKeyboardFocus),
            "native_handle": native_handle,
            "runtime_id": runtime_id,
            "read_only": None,
            "text_value": None,
            "supports_text": False,
        }

        try:
            value_pattern = element.GetCurrentPattern(UIA.UIA_ValuePatternId).QueryInterface(
                UIA.IUIAutomationValuePattern
            )
            info["read_only"] = bool(value_pattern.CurrentIsReadOnly)
            info["text_value"] = str(value_pattern.CurrentValue or "")
        except Exception:
            pass

        try:
            text_pattern = element.GetCurrentPattern(UIA.UIA_TextPatternId).QueryInterface(
                UIA.IUIAutomationTextPattern
            )
            document_range = text_pattern.DocumentRange
            info["supports_text"] = True
            info["text_value"] = str(document_range.GetText(-1) or "")
            if info["read_only"] is None:
                read_only = document_range.GetAttributeValue(UIA.UIA_IsReadOnlyAttributeId)
                if isinstance(read_only, bool):
                    info["read_only"] = read_only
        except Exception:
            pass

        if info["read_only"] is None and native_handle:
            try:
                style = ctypes.windll.user32.GetWindowLongW(native_handle, -16)
                if info["control_type"] == WINDOWS_EDIT_CONTROL_TYPE:
                    info["read_only"] = bool(style & 0x0800)  # ES_READONLY
            except Exception:
                pass
        return info
    except Exception as exc:
        print(f"[SafeTextEntry] Windows UI Automation probe failed: {type(exc).__name__}")
        return {}
    finally:
        if com_initialized and comtypes_module is not None:
            try:
                comtypes_module.CoUninitialize()
            except Exception:
                pass


def _windows_target_id(info: dict) -> tuple:
    return (
        int(info.get("process_id") or 0),
        tuple(info.get("runtime_id") or ()),
        int(info.get("control_type") or 0),
        str(info.get("automation_id") or ""),
        str(info.get("class_name") or ""),
    )


def _validate_windows_text_target(info: dict, purpose: str = "generic") -> SafeTextEntryResult:
    if not info:
        return SafeTextEntryResult(False, "No puedo verificar un campo de texto enfocado en Windows.")

    process = str(info.get("process_name") or "").casefold()
    class_name = str(info.get("class_name") or "").casefold()
    control_type = int(info.get("control_type") or 0)
    if process in WINDOWS_BLOCKED_PROCESSES:
        return SafeTextEntryResult(False, "No escribiré en esa aplicación protegida.")
    if class_name in WINDOWS_DESKTOP_CLASSES or (
        process == "explorer.exe" and control_type not in {WINDOWS_EDIT_CONTROL_TYPE, WINDOWS_DOCUMENT_CONTROL_TYPE}
    ):
        return SafeTextEntryResult(False, "El escritorio no es un destino de texto editable.")
    if not info.get("enabled") or not info.get("keyboard_focusable") or not info.get("has_keyboard_focus"):
        return SafeTextEntryResult(False, "No hay un control de texto editable con el foco confirmado.")
    if control_type not in {WINDOWS_EDIT_CONTROL_TYPE, WINDOWS_DOCUMENT_CONTROL_TYPE}:
        return SafeTextEntryResult(False, "El elemento enfocado no es un campo de texto editable.")
    if info.get("read_only") is True:
        return SafeTextEntryResult(False, "El campo de texto enfocado es de solo lectura.")

    label = " ".join(str(info.get(key) or "") for key in ("name", "automation_id", "class_name")).casefold()
    browser_processes = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"}
    if process in browser_processes and any(
        marker in label for marker in ("address and search bar", "address bar", "omnibox", "barra de direcciones")
    ):
        return SafeTextEntryResult(False, "No escribiré en la barra de direcciones del navegador.")
    if str(purpose or "generic").casefold() == "message":
        message_markers = MESSAGE_LABEL_MARKERS + ("compose", "composer", "redactar", "mensaje", "responder")
        if not _contains_any(label, message_markers):
            return SafeTextEntryResult(False, "No puedo confirmar que el campo enfocado sea un compositor de mensajes.")

    # ValuePattern exposes read-only state for standard/browser edit controls.
    # Modern Notepad exposes a focused Document/TextPattern instead.
    known_notepad_document = (
        process == "notepad.exe"
        and control_type == WINDOWS_DOCUMENT_CONTROL_TYPE
        and bool(info.get("supports_text"))
    )
    if info.get("read_only") is None and not known_notepad_document:
        return SafeTextEntryResult(False, "No puedo determinar con seguridad si el campo permite edición.")

    target_id = _windows_target_id(info)
    if not target_id[0] or not target_id[1]:
        return SafeTextEntryResult(False, "No puedo identificar de forma estable el campo enfocado.")
    target_label = str(info.get("name") or info.get("class_name") or "campo de texto")
    return SafeTextEntryResult(
        True,
        "Campo de texto editable verificado en Windows.",
        f"{info.get('process_name') or 'Windows'} {target_label}",
        safety_path="windows_uia",
        target_id=target_id,
        readback_supported=info.get("text_value") is not None,
    )


def _windows_focus_matches(target_id: tuple) -> bool:
    current = _windows_focused_element_info()
    return bool(current and _windows_target_id(current) == target_id)


def _windows_send_input(units: list[tuple[int, int]]) -> bool:
    """Send keyboard inputs, where each tuple is (virtual-key, scan-code/UTF-16 unit)."""
    ulong_ptr = wintypes.WPARAM

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ulong_ptr),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

    key_up = 0x0002
    unicode_flag = 0x0004
    inputs: list[INPUT] = []
    for virtual_key, scan_code in units:
        flags = unicode_flag if not virtual_key else 0
        inputs.append(INPUT(type=1, ki=KEYBDINPUT(virtual_key, scan_code, flags, 0, 0)))
        inputs.append(INPUT(type=1, ki=KEYBDINPUT(virtual_key, scan_code, flags | key_up, 0, 0)))
    if not inputs:
        return True
    array = (INPUT * len(inputs))(*inputs)
    sent = ctypes.windll.user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    return int(sent) == len(inputs)


def _write_windows_unicode(text: str, target_id: tuple) -> tuple[bool, str]:
    """Write Unicode natively while rechecking focused UIA identity before each character."""
    for character in text:
        if not _windows_focus_matches(target_id):
            return False, "El foco cambió o el campo de texto desapareció; se detuvo la escritura."
        if character == "\n":
            if not _windows_send_input([(0x0D, 0)]):
                return False, "Windows no pudo insertar el salto de línea."
            continue
        utf16 = character.encode("utf-16-le")
        units = [int.from_bytes(utf16[index:index + 2], "little") for index in range(0, len(utf16), 2)]
        if not _windows_send_input([(0, unit) for unit in units]):
            return False, "Windows no pudo insertar el texto Unicode."
    return True, ""


def _frontmost_app_name() -> str:
    if _actual_os() != "mac":
        return ""
    try:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return str(app.localizedName() or "").strip() if app else ""
    except Exception:
        pass

    script = 'tell application "System Events" to return name of first application process whose frontmost is true'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


class MouseClickBlocker:
    """Temporarily swallows user mouse clicks while JARVIS is typing."""

    def __init__(self):
        self._quartz = None
        self._tap = None
        self._source = None
        self._run_loop = None
        self._thread = None
        self._callback = None

    def __enter__(self):
        if _actual_os() == "mac":
            self._start_mac_tap()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()

    def _start_mac_tap(self) -> None:
        try:
            import Quartz
        except Exception as e:
            print(f"[SafeTextEntry] Mouse click lock unavailable: {e}")
            return

        click_events = (
            Quartz.kCGEventLeftMouseDown,
            Quartz.kCGEventLeftMouseUp,
            Quartz.kCGEventRightMouseDown,
            Quartz.kCGEventRightMouseUp,
            Quartz.kCGEventOtherMouseDown,
            Quartz.kCGEventOtherMouseUp,
        )
        mask = 0
        for event_type in click_events:
            mask |= Quartz.CGEventMaskBit(event_type)

        def _swallow(proxy, event_type, event, refcon):
            if event_type in click_events:
                return None
            return event

        try:
            self._quartz = Quartz
            self._callback = _swallow
            self._tap = Quartz.CGEventTapCreate(
                Quartz.kCGHIDEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionDefault,
                mask,
                _swallow,
                None,
            )
            if not self._tap:
                print("[SafeTextEntry] Mouse click lock unavailable; grant Accessibility permission.")
                return

            self._source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)

            def _run():
                self._run_loop = Quartz.CFRunLoopGetCurrent()
                Quartz.CFRunLoopAddSource(
                    self._run_loop,
                    self._source,
                    Quartz.kCFRunLoopCommonModes,
                )
                Quartz.CGEventTapEnable(self._tap, True)
                Quartz.CFRunLoopRun()

            self._thread = threading.Thread(target=_run, daemon=True)
            self._thread.start()
            time.sleep(0.04)
        except Exception as e:
            print(f"[SafeTextEntry] Mouse click lock failed: {e}")
            self.stop()

    def stop(self) -> None:
        if not self._quartz:
            return
        try:
            if self._tap:
                self._quartz.CGEventTapEnable(self._tap, False)
            if self._run_loop:
                self._quartz.CFRunLoopStop(self._run_loop)
        except Exception:
            pass


class PyAutoGuiFastPause:
    def __enter__(self):
        self._previous_pause = getattr(pyautogui, "PAUSE", 0)
        pyautogui.PAUSE = 0.0
        return self

    def __exit__(self, exc_type, exc, tb):
        pyautogui.PAUSE = self._previous_pause
        return False


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in markers)


def _browser_dom_focus_info() -> dict:
    if _actual_os() != "mac":
        return {}

    dom_js = r"""
(() => {
  const visible = (candidate) => {
    if (!candidate || !candidate.getBoundingClientRect) return false;
    const rect = candidate.getBoundingClientRect();
    const style = window.getComputedStyle(candidate);
    return rect.width > 20 && rect.height > 10 && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const describe = (el) => {
    if (!el) return {ok: false};
    const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : {};
    const label = [
      el.getAttribute && el.getAttribute('aria-label'),
      el.getAttribute && el.getAttribute('placeholder'),
      el.getAttribute && el.getAttribute('name'),
      el.getAttribute && el.getAttribute('role'),
      el.innerText,
      el.textContent
    ].filter(Boolean).join(' ').slice(0, 240);
    return {
      ok: true,
      tag: (el.tagName || '').toLowerCase(),
      type: ((el.getAttribute && el.getAttribute('type')) || '').toLowerCase(),
      role: ((el.getAttribute && el.getAttribute('role')) || '').toLowerCase(),
      label,
      isContentEditable: !!el.isContentEditable,
      rect: {
        left: Math.round(rect.left || 0),
        top: Math.round(rect.top || 0),
        width: Math.round(rect.width || 0),
        height: Math.round(rect.height || 0),
        bottom: Math.round(rect.bottom || 0)
      },
      viewportHeight: window.innerHeight || 0,
      url: location.href
    };
  };
  const composerCandidates = Array.from(document.querySelectorAll(
    'div[contenteditable="true"][role="textbox"], div[contenteditable="true"], textarea, input[type="text"]'
  )).filter(visible);
  const composer = composerCandidates.filter(el => {
    const label = [
      el.getAttribute && el.getAttribute('aria-label'),
      el.getAttribute && el.getAttribute('placeholder'),
      el.getAttribute && el.getAttribute('role')
    ].filter(Boolean).join(' ').toLowerCase();
    const rect = el.getBoundingClientRect();
    return label.includes('message') || label.includes('reply') || rect.bottom > window.innerHeight * 0.55;
  }).sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom)[0] || null;

  const active = describe(document.activeElement);
  const composerInfo = describe(composer);
  if (composer && document.activeElement !== composer && location.href.includes('/direct')) {
    try { composer.focus(); } catch (e) {}
  }
  return JSON.stringify({
    ok: true,
    active,
    composer: composerInfo,
    composerFound: !!composer,
    url: location.href
  });
})()
"""
    active_js = r"""
(() => {
  const el = document.activeElement;
  if (!el) return JSON.stringify({ok: false});
  const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : {};
  const label = [
    el.getAttribute && el.getAttribute('aria-label'),
    el.getAttribute && el.getAttribute('placeholder'),
    el.getAttribute && el.getAttribute('name'),
    el.getAttribute && el.getAttribute('role'),
    el.innerText,
    el.textContent
  ].filter(Boolean).join(' ').slice(0, 240);
  return JSON.stringify({
    ok: true,
    tag: (el.tagName || '').toLowerCase(),
    type: ((el.getAttribute && el.getAttribute('type')) || '').toLowerCase(),
    role: ((el.getAttribute && el.getAttribute('role')) || '').toLowerCase(),
    label,
    isContentEditable: !!el.isContentEditable,
    rect: {
      left: Math.round(rect.left || 0),
      top: Math.round(rect.top || 0),
      width: Math.round(rect.width || 0),
      height: Math.round(rect.height || 0),
      bottom: Math.round(rect.bottom || 0)
    },
    viewportHeight: window.innerHeight || 0,
    url: location.href
  });
})()
"""
    script = f"""
function chromeLike(name) {{
  try {{
    const app = Application(name);
    if (!app.running()) return '';
    const windows = app.windows();
    for (let i = 0; i < windows.length; i++) {{
      const tab = windows[i].activeTab();
      const url = tab.url();
      if ((url || '').indexOf('instagram.com/direct') >= 0) {{
        const raw = tab.execute({{javascript: {json.dumps(dom_js)}}});
        const info = JSON.parse(raw || '{{}}');
        return JSON.stringify({{frontApp: name, url, dom: info.composerFound ? info.composer : info.active, browserInfo: info}});
      }}
    }}
    if (windows.length) {{
      const tab = windows[0].activeTab();
      const url = tab.url();
      const raw = tab.execute({{javascript: {json.dumps(active_js)}}});
      const dom = JSON.parse(raw || '{{}}');
      return JSON.stringify({{frontApp: name, url, dom}});
    }}
  }} catch (e) {{}}
  return '';
}}

function safari() {{
  try {{
    const app = Application('Safari');
    if (!app.running()) return '';
    const windows = app.windows();
    for (let i = 0; i < windows.length; i++) {{
      const tab = windows[i].currentTab();
      const url = tab.url();
      if ((url || '').indexOf('instagram.com/direct') >= 0) {{
        const raw = app.doJavaScript({json.dumps(dom_js)}, {{in: tab}});
        const info = JSON.parse(raw || '{{}}');
        return JSON.stringify({{frontApp: 'Safari', url, dom: info.composerFound ? info.composer : info.active, browserInfo: info}});
      }}
    }}
    if (windows.length) {{
      const tab = windows[0].currentTab();
      const url = tab.url();
      const raw = app.doJavaScript({json.dumps(active_js)}, {{in: tab}});
      const dom = JSON.parse(raw || '{{}}');
      return JSON.stringify({{frontApp: 'Safari', url, dom}});
    }}
  }} catch (e) {{}}
  return '';
}}

(() => {{
  const browsers = ['Google Chrome', 'Brave Browser', 'Microsoft Edge', 'Arc'];
  for (let i = 0; i < browsers.length; i++) {{
    const result = chromeLike(browsers[i]);
    if (result) return result;
  }}
  const safariResult = safari();
  if (safariResult) return safariResult;
  return JSON.stringify({{frontApp: '', url: '', dom: {{ok: false}}}});
}})();
"""
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception as e:
        print(f"[SafeTextEntry] Browser safety probe failed: {e}")
        return {}

    if result.returncode != 0:
        error = (result.stderr or result.stdout or "").strip()
        if error:
            print(f"[SafeTextEntry] Browser safety probe error: {error}")
        return {}
    try:
        return json.loads(result.stdout.strip() or "{}")
    except Exception as e:
        print(f"[SafeTextEntry] Browser safety probe parse failed: {e}: {result.stdout.strip()[:200]}")
        return {}


def _accessibility_focus_info() -> dict:
    if _actual_os() != "mac":
        return {}

    script = r'''
tell application "System Events"
    set frontProcess to first application process whose frontmost is true
    set frontApp to name of frontProcess
    set roleValue to ""
    set subroleValue to ""
    set titleValue to ""
    set descriptionValue to ""
    set valueValue to ""
    tell frontProcess
        try
            set focusedElement to value of attribute "AXFocusedUIElement"
        end try
        try
            set roleValue to value of attribute "AXRole" of focusedElement as text
        end try
        try
            set subroleValue to value of attribute "AXSubrole" of focusedElement as text
        end try
        try
            set titleValue to value of attribute "AXTitle" of focusedElement as text
        end try
        try
            set descriptionValue to value of attribute "AXDescription" of focusedElement as text
        end try
        try
            set valueValue to value of attribute "AXValue" of focusedElement as text
        end try
    end tell
    return frontApp & linefeed & roleValue & linefeed & subroleValue & linefeed & titleValue & linefeed & descriptionValue & linefeed & valueValue
end tell
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception as e:
        print(f"[SafeTextEntry] Accessibility safety probe failed: {e}")
        return {}

    if result.returncode != 0:
        error = (result.stderr or result.stdout or "").strip()
        if error:
            print(f"[SafeTextEntry] Accessibility safety probe error: {error}")
        return {}
    lines = (result.stdout or "").splitlines()
    while len(lines) < 6:
        lines.append("")
    return {
        "frontApp": lines[0].strip(),
        "role": lines[1].strip(),
        "subrole": lines[2].strip(),
        "title": lines[3].strip(),
        "description": lines[4].strip(),
        "value": lines[5].strip(),
    }


def _dom_textish(dom: dict) -> bool:
    tag = str(dom.get("tag", "")).lower()
    input_type = str(dom.get("type", "")).lower()
    role = str(dom.get("role", "")).lower()
    return (
        tag == "textarea"
        or role in {"textbox", "searchbox"}
        or bool(dom.get("isContentEditable"))
        or (tag == "input" and input_type in {"", "text", "search", "email", "tel", "url", "password"})
    )


def _dom_message_composer(info: dict) -> bool:
    url = str(info.get("url") or info.get("dom", {}).get("url") or "").lower()
    dom = info.get("dom") or {}
    if not _dom_textish(dom):
        return False
    if not _contains_any(url, MESSAGING_URL_MARKERS):
        return False
    label = " ".join(str(dom.get(k, "")) for k in ("label", "role", "tag"))
    if _contains_any(label, MESSAGE_LABEL_MARKERS):
        return True
    rect = dom.get("rect") or {}
    try:
        viewport_height = float(dom.get("viewportHeight") or 0)
        bottom = float(rect.get("bottom") or 0)
        return viewport_height > 0 and bottom > viewport_height * 0.55
    except Exception:
        return False


def _pointer_message_target() -> SafeTextEntryResult:
    _require_pyautogui()
    front_app = _frontmost_app_name()
    if front_app in UNSAFE_TYPING_APPS:
        return SafeTextEntryResult(False, f"I will not type into {front_app}; that app is blocked for safety.")

    x, y = pyautogui.position()
    width, height = pyautogui.size()
    if height <= 0 or width <= 0:
        return SafeTextEntryResult(False, "I cannot verify the screen bounds. Click the message box and try again.")
    if y < height * 0.45:
        return SafeTextEntryResult(
            False,
            "Your pointer is not in the message area. Put the pointer over the message box and try again.",
        )
    if x < width * 0.18:
        return SafeTextEntryResult(
            False,
            "Your pointer looks too close to the sidebar. Put it over the message box and try again.",
        )

    return SafeTextEntryResult(
        True,
        "Using pointer-confirmed message area.",
        f"{front_app or 'pointer'} {int(x)},{int(y)}",
        click_before_typing=True,
        safety_path="pointer_message_fallback",
    )


def validate_safe_text_target(purpose: str = "generic", allow_pointer_fallback: bool = False) -> SafeTextEntryResult:
    purpose_key = str(purpose or "generic").lower().strip()
    os_name = _actual_os()
    if os_name == "windows":
        return _validate_windows_text_target(_windows_focused_element_info(), purpose_key)
    if os_name != "mac":
        return SafeTextEntryResult(False, "Safe text-field validation is unavailable on this operating system.")

    dom_info = _browser_dom_focus_info()
    front_app = str(dom_info.get("frontApp", "")).strip()
    dom = dom_info.get("dom") or {}
    if front_app in BROWSER_APPS and dom.get("ok") and _dom_textish(dom):
        label = " ".join(str(dom.get(k, "")) for k in ("label", "role", "tag"))
        url = str(dom_info.get("url") or dom.get("url") or "")
        if _contains_any(label, ADDRESS_LABEL_MARKERS):
            return SafeTextEntryResult(False, "I will not type because the browser address/search bar appears to be focused.")
        if purpose_key == "message":
            if _dom_message_composer(dom_info):
                return SafeTextEntryResult(True, "Safe browser message composer focused.", f"{front_app} {url}", safety_path="browser_dom")
            if allow_pointer_fallback:
                return _pointer_message_target()
            return SafeTextEntryResult(False, "I do not see a safe message composer focused. Click the message box and try again.")
        return SafeTextEntryResult(True, "Safe browser text field focused.", f"{front_app} {url}", safety_path="browser_dom")

    ax = _accessibility_focus_info()
    front_app = str(ax.get("frontApp", "")).strip()
    role = str(ax.get("role", "")).strip()
    label = " ".join(str(ax.get(k, "")) for k in ("title", "description", "value", "role", "subrole"))

    if not front_app or not role:
        if purpose_key == "message" and allow_pointer_fallback:
            return _pointer_message_target()
        return SafeTextEntryResult(False, "I cannot verify a safe focused text field. Click the text box and try again.")
    if front_app in UNSAFE_TYPING_APPS:
        return SafeTextEntryResult(False, f"I will not type into {front_app}; that app is blocked for safety.")
    if role not in TEXT_ROLES:
        return SafeTextEntryResult(False, "I do not see a safe text field focused. Click the text box and try again.")
    if _contains_any(label, ADDRESS_LABEL_MARKERS):
        return SafeTextEntryResult(False, "I will not type because an address/search field appears to be focused.")

    if purpose_key == "message":
        if front_app in MESSAGING_APPS or _contains_any(label, MESSAGE_LABEL_MARKERS):
            return SafeTextEntryResult(True, "Safe message field focused.", f"{front_app} {role}", safety_path="accessibility")
        if allow_pointer_fallback:
            return _pointer_message_target()
        return SafeTextEntryResult(False, "I do not see a safe message composer focused. Click the message box and try again.")

    return SafeTextEntryResult(True, "Safe text field focused.", f"{front_app} {role}", safety_path="accessibility")


def _write_visible_line(line: str, interval: float) -> None:
    try:
        pyautogui.write(line, interval=interval)
        return
    except Exception:
        pass

    for ch in str(line or ""):
        pyautogui.write(ch, interval=interval)


def safe_type_text(
    text: str,
    *,
    purpose: str = "generic",
    press_enter: bool = False,
    clear_first: bool = False,
    allow_pointer_fallback: bool = False,
    interval: float = VISIBLE_TYPING_INTERVAL_SECONDS,
) -> SafeTextEntryResult:
    _require_pyautogui()
    if not str(text or ""):
        return SafeTextEntryResult(False, "No se proporcionó texto para escribir.")
    validation = validate_safe_text_target(purpose, allow_pointer_fallback=allow_pointer_fallback)
    if not validation.ok:
        print(
            f"[SafeTextEntry] refused purpose={purpose} "
            f"reason={validation.message} target={validation.target or 'none'}"
        )
        return validation

    os_name = _actual_os()
    select_all = ("command", "a") if os_name == "mac" else ("ctrl", "a")
    print(
        f"[SafeTextEntry] path={validation.safety_path or 'unknown'} "
        f"purpose={purpose} target={validation.target or 'unknown'}"
    )

    if os_name == "windows":
        before_info = _windows_focused_element_info()
        if not before_info or _windows_target_id(before_info) != validation.target_id:
            return SafeTextEntryResult(False, "El foco cambió después de validar el campo; no se escribió texto.")
        before_text = before_info.get("text_value")
        with PyAutoGuiFastPause():
            if clear_first:
                pyautogui.hotkey(*select_all)
                time.sleep(0.03)
                pyautogui.press("delete")
                time.sleep(0.03)
                if not _windows_focus_matches(validation.target_id):
                    return SafeTextEntryResult(False, "El foco cambió al preparar el campo; no se escribió texto.")

            wrote, error = _write_windows_unicode(str(text), validation.target_id)
            if not wrote:
                return SafeTextEntryResult(False, error, validation.target, safety_path="windows_uia")
            if press_enter:
                if not _windows_focus_matches(validation.target_id):
                    return SafeTextEntryResult(False, "El foco cambió antes de confirmar; no se pulsó Intro.")
                if not _windows_send_input([(0x0D, 0)]):
                    return SafeTextEntryResult(False, "Windows no pudo pulsar Intro en el campo verificado.")

        after_info = _windows_focused_element_info()
        if not after_info or _windows_target_id(after_info) != validation.target_id:
            return SafeTextEntryResult(False, "El campo validado desapareció antes de comprobar el resultado.")
        if validation.readback_supported:
            after_text = after_info.get("text_value")
            expected = str(text).replace("\r\n", "\n")
            normalized_after = str(after_text or "").replace("\r\n", "\n")
            normalized_before = str(before_text or "").replace("\r\n", "\n")
            if normalized_after == normalized_before or expected not in normalized_after:
                return SafeTextEntryResult(False, "Windows recibió la entrada, pero no pude verificar el texto insertado.")
            return SafeTextEntryResult(
                True,
                "Texto escrito de forma segura y verificado en el campo enfocado.",
                validation.target,
                safety_path="windows_uia_verified",
                target_id=validation.target_id,
                readback_supported=True,
            )
        return SafeTextEntryResult(
            True,
            "Texto enviado al campo enfocado verificado; este control no permite releer la inserción.",
            validation.target,
            safety_path="windows_uia_no_readback",
            target_id=validation.target_id,
        )

    with MouseClickBlocker(), PyAutoGuiFastPause():
        if validation.click_before_typing:
            pyautogui.click()
            time.sleep(0.08)
            clicked_app = _frontmost_app_name()
            if clicked_app in UNSAFE_TYPING_APPS:
                return SafeTextEntryResult(False, f"I will not type into {clicked_app}; that app is blocked for safety.")
            if purpose == "message" and clicked_app and clicked_app not in SAFE_POINTER_MESSAGE_APPS:
                return SafeTextEntryResult(
                    False,
                    f"I clicked the pointer location, but {clicked_app} is not a supported messaging target.",
                )

        if clear_first:
            pyautogui.hotkey(*select_all)
            time.sleep(0.03)
            pyautogui.press("delete")
            time.sleep(0.03)

        lines = str(text or "").split("\n")
        for index, line in enumerate(lines):
            if line:
                _write_visible_line(line, interval)
            if index < len(lines) - 1:
                pyautogui.hotkey("shift", "enter")
                time.sleep(interval)

        if press_enter:
            time.sleep(0.03)
            pyautogui.press("enter")
            time.sleep(0.12)

    action = "sent" if press_enter else "typed"
    return SafeTextEntryResult(True, f"Safely {action} text.", validation.target)


def safe_type_then_enter(
    text: str,
    *,
    purpose: str = "message",
    allow_pointer_fallback: bool = False,
) -> SafeTextEntryResult:
    return safe_type_text(
        text,
        purpose=purpose,
        press_enter=True,
        allow_pointer_fallback=allow_pointer_fallback,
    )
