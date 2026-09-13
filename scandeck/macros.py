"""Macros clavier : enregistrement, stockage, lecture vers Elite.

Chaque joueur a son propre fichier (jamais dans git) :
  Linux    ~/.local/share/ScanDeck/macros.json
  Windows  Documents/ScanDeck/macros.json

Une macro = nom + touche de lancement + étapes
  {"key", "hold_ms"}  appui ou maintien
  {"delay_ms"}        pause ; à la lecture on ignore celles > 0,2 s
                      (temps mort pendant l’enregistrement, pas un ordre)

Linux   : XTEST / xdotool, écoute XI2 (la touche marche même si Elite a le focus).
Windows : SendInput en scancodes, hook clavier bas niveau (équivalent XI2).

Pour que le maintien tienne en jeu : Elite en fenêtré ou borderless, et la
touche de lancement non assignée dans les contrôles Elite.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from .config import user_data_dir

# Un appui plus court que ça s’affiche comme un tap, pas un maintien.
HOLD_TAP_MS = 70
# Relancer keydown / revérifier le focus pendant un long maintien.
HOLD_REFRESH_S = 0.04
FOCUS_CHECK_S = 0.12
# Petit trou entre deux touches à la lecture (après une pause d’enregistrement ignorée).
INTER_KEY_S = 0.08
MAX_PLAY_DELAY_S = 0.20
# Noms xdotool pour les touches spéciales (lettres/chiffres passent tels quels).
XDOTOOL_NAMES = {
    "space": "space",
    "BackSpace": "BackSpace",
    "Return": "Return",
    "Tab": "Tab",
    "Escape": "Escape",
    "Delete": "Delete",
    "Insert": "Insert",
    "Home": "Home",
    "End": "End",
    "Prior": "Page_Up",
    "Next": "Page_Down",
    "Left": "Left",
    "Right": "Right",
    "Up": "Up",
    "Down": "Down",
    "Shift_L": "Shift_L",
    "Shift_R": "Shift_R",
    "Control_L": "Control_L",
    "Control_R": "Control_R",
    "Alt_L": "Alt_L",
    "Alt_R": "Alt_R",
    "plus": "plus",
    "minus": "minus",
    "equal": "equal",
    "comma": "comma",
    "period": "period",
    "slash": "slash",
    "backslash": "backslash",
    "semicolon": "semicolon",
    "apostrophe": "apostrophe",
    "bracketleft": "bracketleft",
    "bracketright": "bracketright",
    "grave": "grave",
}
# Virtual-keys Windows (lettres/chiffres : ord('A') / ord('0') dans _win_vk).
WIN_VK = {
    "space": 0x20,
    "BackSpace": 0x08,
    "Return": 0x0D,
    "Tab": 0x09,
    "Escape": 0x1B,
    "Delete": 0x2E,
    "Insert": 0x2D,
    "Home": 0x24,
    "End": 0x23,
    "Prior": 0x21,
    "Next": 0x22,
    "Left": 0x25,
    "Up": 0x26,
    "Right": 0x27,
    "Down": 0x28,
    "Shift_L": 0xA0,
    "Shift_R": 0xA1,
    "Control_L": 0xA2,
    "Control_R": 0xA3,
    "Alt_L": 0xA4,
    "Alt_R": 0xA5,
    "KP_0": 0x60,
    "KP_1": 0x61,
    "KP_2": 0x62,
    "KP_3": 0x63,
    "KP_4": 0x64,
    "KP_5": 0x65,
    "KP_6": 0x66,
    "KP_7": 0x67,
    "KP_8": 0x68,
    "KP_9": 0x69,
    "KP_Decimal": 0x6E,
    "KP_Add": 0x6B,
    "KP_Subtract": 0x6D,
    "KP_Multiply": 0x6A,
    "KP_Divide": 0x6F,
    "KP_Enter": 0x0D,
    "KP_Insert": 0x2D,
    "KP_Delete": 0x2E,
    "KP_End": 0x23,
    "KP_Down": 0x28,
    "KP_Next": 0x22,
    "KP_Left": 0x25,
    "KP_Begin": 0x0C,
    "KP_Right": 0x27,
    "KP_Home": 0x24,
    "KP_Up": 0x26,
    "KP_Prior": 0x21,
}

_play_lock = threading.Lock()
_playing = False  # une seule lecture à la fois (évite deux macros en parallèle)


def macros_path() -> Path:
    """Fichier perso des macros, à côté de config.json."""
    return user_data_dir() / "macros.json"


def load_macros() -> list[dict]:
    path = macros_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for row in data:
        if isinstance(row, dict) and row.get("name") and isinstance(row.get("steps"), list):
            out.append(row)
    return out


def save_macros(rows: list[dict]) -> None:
    macros_path().write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def upsert_macro(macro: dict, *, replace_id: str | None = None) -> list[dict]:
    rows = load_macros()
    mid = replace_id or macro.get("id") or uuid.uuid4().hex[:10]
    macro = dict(macro)
    macro["id"] = mid
    found = False
    for i, row in enumerate(rows):
        if row.get("id") == mid:
            rows[i] = macro
            found = True
            break
    if not found:
        rows.append(macro)
    save_macros(rows)
    return rows


def delete_macro(macro_id: str) -> list[dict]:
    rows = [row for row in load_macros() if row.get("id") != macro_id]
    save_macros(rows)
    return rows


def pretty_key(key: str) -> str:
    """Libellé HUD : r → R, KP_0 → Num0."""
    aliases = {
        "space": "Space",
        "BackSpace": "BackSpace",
        "Return": "Enter",
        "Tab": "Tab",
        "Left": "←",
        "Right": "→",
        "Up": "↑",
        "Down": "↓",
        "Prior": "PageUp",
        "Next": "PageDown",
        "Delete": "Del",
        "Escape": "Esc",
        "KP_Add": "Num+",
        "KP_Subtract": "Num-",
        "KP_Multiply": "Num*",
        "KP_Divide": "Num/",
        "KP_Decimal": "Num.",
        "KP_Enter": "NumEnter",
        "KP_Insert": "Num0",
        "KP_Delete": "Num.",
        "KP_End": "Num1",
        "KP_Down": "Num2",
        "KP_Next": "Num3",
        "KP_Left": "Num4",
        "KP_Begin": "Num5",
        "KP_Right": "Num6",
        "KP_Home": "Num7",
        "KP_Up": "Num8",
        "KP_Prior": "Num9",
    }
    if key in aliases:
        return aliases[key]
    if len(key) == 1:
        return key.upper()
    if key.startswith("KP_"):
        return "Num" + key[3:]
    return key


def format_hold_s(ms: int) -> str:
    return f"{max(ms, 0) / 1000.0:.1f} s"


def format_step(step: dict) -> str:
    if "delay_ms" in step:
        return f"+  {format_hold_s(int(step['delay_ms']))}"
    key = pretty_key(step.get("key") or "?")
    hold = int(step.get("hold_ms") or 0)
    if hold > HOLD_TAP_MS:
        return f"{key}  {format_hold_s(hold)}"
    return key


def is_playing() -> bool:
    return _playing


def play_macro(macro: dict, *, on_done=None) -> str | None:
    """Lance la lecture en fond. Erreur immédiate, ou None si ça a démarré."""
    global _playing
    steps = list(macro.get("steps") or [])
    if not steps:
        return "empty"
    if not _play_lock.acquire(blocking=False):
        return "busy"
    _playing = True

    def worker() -> None:
        global _playing
        err = None
        try:
            err = _play_steps(steps)
        except Exception as exc:
            err = str(exc)
        finally:
            _playing = False
            _play_lock.release()
            if on_done:
                on_done(err)

    threading.Thread(target=worker, daemon=True, name="macro-play").start()
    return None


def _play_steps(steps: list[dict]) -> str | None:
    """Backend clavier selon l’OS. Ne pas mélanger xdotool et SendInput."""
    if sys.platform == "win32":
        return _play_windows(steps)
    return _play_linux(steps)


def _play_linux(steps: list[dict]) -> str | None:
    """Trouve la fenêtre Elite, lui donne le focus, rejoue les touches via XTEST."""
    if not _which("xdotool"):
        return "need_xdotool"
    wid = _elite_window()
    if not wid:
        return "no_window"
    sender = _XKeySender()
    try:
        _activate_elite(wid)
        time.sleep(0.25)
        pending_gap = False
        for step in steps:
            if "delay_ms" in step:
                gap = max(0, int(step["delay_ms"])) / 1000.0
                if gap <= MAX_PLAY_DELAY_S:
                    time.sleep(gap)
                    pending_gap = False
                else:
                    pending_gap = True
                continue
            name = _xdo_key(step.get("key") or "")
            if not name:
                continue
            if pending_gap:
                time.sleep(INTER_KEY_S)
                pending_gap = False
            hold = max(HOLD_TAP_MS, int(step.get("hold_ms") or HOLD_TAP_MS))
            _hold_linux(sender, wid, name, hold)
            pending_gap = True
        return None
    finally:
        sender.close()


def _activate_elite(wid: str) -> None:
    _run(["xdotool", "windowactivate", "--sync", wid], timeout=2)
    _run(["xdotool", "windowfocus", wid], timeout=2)


def _elite_focused(wid: str) -> bool:
    proc = _run(["xdotool", "getactivewindow"], timeout=1)
    return bool(proc and proc.stdout.strip() == str(wid))


def _hold_linux(sender: "_XKeySender", wid: str, name: str, hold_ms: int) -> None:
    """Maintien : keydown, refresh XTEST, récupère le focus si ScanDeck l’a volé."""
    _activate_elite(wid)
    sender.down(name)
    if not sender.ok:
        _run(["xdotool", "keydown", name], timeout=1)
    end = time.monotonic() + hold_ms / 1000.0
    next_focus = time.monotonic()
    while True:
        now = time.monotonic()
        if now >= end:
            break
        if now >= next_focus:
            if not _elite_focused(wid):
                _activate_elite(wid)
                sender.down(name)
                if not sender.ok:
                    _run(["xdotool", "keydown", name], timeout=1)
            next_focus = now + FOCUS_CHECK_S
        sender.down(name)
        time.sleep(min(HOLD_REFRESH_S, max(0.0, end - time.monotonic())))
    sender.up(name)
    _run(["xdotool", "keyup", name], timeout=1)


class _XKeySender:
    """XTEST : la touche reste enfoncée au niveau X11 (un tap unique ne suffit pas en jeu)."""

    def __init__(self) -> None:
        self._dpy = None
        self._x11 = None
        self._xtst = None
        if sys.platform == "win32":
            return
        from ctypes.util import find_library

        x11_name = find_library("X11")
        xt_name = find_library("Xtst") or "libXtst.so.6"
        if not x11_name:
            return
        try:
            x11 = ctypes.cdll.LoadLibrary(x11_name)
            xtst = ctypes.cdll.LoadLibrary(xt_name)
        except OSError:
            return
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XStringToKeysym.restype = ctypes.c_ulong
        x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
        x11.XKeysymToKeycode.restype = ctypes.c_uint
        x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xtst.XTestFakeKeyEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong,
        ]
        dpy = x11.XOpenDisplay(None)
        if not dpy:
            return
        self._x11 = x11
        self._xtst = xtst
        self._dpy = dpy

    @property
    def ok(self) -> bool:
        return bool(self._dpy)

    def _code(self, name: str) -> int:
        if not self._dpy or not self._x11:
            return 0
        ks = self._x11.XStringToKeysym(name.encode("ascii", "replace"))
        if not ks and len(name) == 1:
            ks = self._x11.XStringToKeysym(name.lower().encode("ascii", "replace"))
        if not ks:
            return 0
        return int(self._x11.XKeysymToKeycode(self._dpy, ks))

    def down(self, name: str) -> None:
        code = self._code(name)
        if not code or not self._dpy or not self._xtst:
            return
        self._xtst.XTestFakeKeyEvent(self._dpy, code, 1, 0)
        self._x11.XFlush(self._dpy)

    def up(self, name: str) -> None:
        code = self._code(name)
        if not code or not self._dpy or not self._xtst:
            return
        self._xtst.XTestFakeKeyEvent(self._dpy, code, 0, 0)
        self._x11.XFlush(self._dpy)

    def close(self) -> None:
        if self._dpy and self._x11:
            try:
                self._x11.XCloseDisplay(self._dpy)
            except Exception:
                pass
        self._dpy = None


def _play_windows(steps: list[dict]) -> str | None:
    """Même séquence que Linux, via SendInput + focus de la fenêtre Elite."""
    hwnd = _elite_hwnd()
    if not hwnd:
        return "no_window"
    _activate_elite_win(hwnd)
    time.sleep(0.25)
    pending_gap = False
    for step in steps:
        if "delay_ms" in step:
            gap = max(0, int(step["delay_ms"])) / 1000.0
            if gap <= MAX_PLAY_DELAY_S:
                time.sleep(gap)
                pending_gap = False
            else:
                pending_gap = True
            continue
        vk = _win_vk(step.get("key") or "")
        if vk is None:
            continue
        if pending_gap:
            time.sleep(INTER_KEY_S)
            pending_gap = False
        hold = max(HOLD_TAP_MS, int(step.get("hold_ms") or HOLD_TAP_MS))
        _hold_windows(hwnd, vk, hold)
        pending_gap = True
    return None


def _xdo_key(keysym: str) -> str:
    if keysym in XDOTOOL_NAMES:
        return XDOTOOL_NAMES[keysym]
    if len(keysym) == 1:
        return keysym
    if keysym.startswith("F") and keysym[1:].isdigit():
        return keysym
    if keysym.isdigit():
        return keysym
    return keysym


def _elite_window() -> str:
    """Id xdotool de Elite - Dangerous (CLIENT), pas le lanceur."""
    proc = _run(["xdotool", "search", "--onlyvisible", "--name", "Elite"], timeout=3)
    wids = [w for w in (proc.stdout.split() if proc and proc.returncode == 0 else []) if w.isdigit()]
    if not wids:
        proc = _run(["xdotool", "search", "--name", "Elite"], timeout=3)
        wids = [w for w in (proc.stdout.split() if proc and proc.returncode == 0 else []) if w.isdigit()]
    best = ""
    best_score = -999
    for wid in wids:
        name_proc = _run(["xdotool", "getwindowname", wid], timeout=2)
        name = (name_proc.stdout if name_proc else "").strip().lower()
        if not name or "scandeck" in name:
            continue
        score = 0
        if "client" in name:
            score += 20
        if "dangerous" in name:
            score += 10
        if "lanceur" in name or "launcher" in name:
            score -= 20
        if score > best_score:
            best_score = score
            best = wid
    return best


def _which(name: str) -> bool:
    from shutil import which
    return which(name) is not None


def _run(cmd: list[str], timeout: int = 5):
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _win_vk(keysym: str) -> int | None:
    """Tk keysym (r, KP_0, F5…) → virtual-key Windows."""
    if keysym in WIN_VK:
        return WIN_VK[keysym]
    if len(keysym) == 1:
        ch = keysym.upper()
        if "A" <= ch <= "Z" or "0" <= ch <= "9":
            return ord(ch)
    if keysym.startswith("KP_") and len(keysym) == 4 and keysym[3].isdigit():
        return 0x60 + int(keysym[3])
    if keysym.startswith("F") and keysym[1:].isdigit():
        n = int(keysym[1:])
        if 1 <= n <= 24:
            return 0x70 + n - 1
    return None


# Flèches, Inser, pavé / : bit KEYEVENTF_EXTENDEDKEY pour SendInput.
_WIN_EXTENDED_VK = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
    0x2D, 0x2E, 0x6F, 0xA3, 0xA5,
}


def _win_send(vk: int, *, down: bool) -> None:
    """Envoi scancode : Elite (DirectInput) ignore souvent le virtual-key seul."""
    import ctypes
    user32 = ctypes.windll.user32
    scan = int(user32.MapVirtualKeyW(vk, 0))
    flags = 0x0008  # KEYEVENTF_SCANCODE
    if vk in _WIN_EXTENDED_VK:
        flags |= 0x0001  # KEYEVENTF_EXTENDEDKEY
    if not down:
        flags |= 0x0002  # KEYEVENTF_KEYUP
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))


def _elite_hwnd() -> int:
    """HWND de la fenêtre Elite (score : CLIENT / Dangerous, ignore ScanDeck)."""
    import ctypes
    user32 = ctypes.windll.user32
    found: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _lparam) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        name = buf.value.lower()
        if "scandeck" in name:
            return True
        score = 0
        if "client" in name:
            score += 20
        if "dangerous" in name:
            score += 10
        if "elite" in name:
            score += 1
        if "lanceur" in name or "launcher" in name:
            score -= 20
        if score > 0:
            found.append((score, int(hwnd)))
        return True

    user32.EnumWindows(callback, 0)
    if not found:
        return 0
    found.sort()
    return found[-1][1]


def _activate_elite_win(hwnd: int) -> None:
    """AttachThreadInput : SetForegroundWindow seul échoue souvent depuis un overlay."""
    import ctypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    cur_tid = kernel32.GetCurrentThreadId()
    if fg_tid and fg_tid != cur_tid:
        user32.AttachThreadInput(fg_tid, cur_tid, True)
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    if fg_tid and fg_tid != cur_tid:
        user32.AttachThreadInput(fg_tid, cur_tid, False)


def _hold_windows(hwnd: int, vk: int, hold_ms: int) -> None:
    """Maintien SendInput ; remet Elite au premier plan si le HUD a pris le focus."""
    import ctypes
    user32 = ctypes.windll.user32
    _activate_elite_win(hwnd)
    _win_send(vk, down=True)
    end = time.monotonic() + hold_ms / 1000.0
    next_focus = time.monotonic()
    while True:
        now = time.monotonic()
        if now >= end:
            break
        if now >= next_focus:
            if int(user32.GetForegroundWindow()) != int(hwnd):
                _activate_elite_win(hwnd)
                _win_send(vk, down=True)
            next_focus = now + FOCUS_CHECK_S
        time.sleep(min(HOLD_REFRESH_S, max(0.0, end - time.monotonic())))
    _win_send(vk, down=False)


if sys.platform == "win32":
    import ctypes

    class KeyBdInput(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class HardwareInput(ctypes.Structure):
        _fields_ = [
            ("uMsg", ctypes.c_ulong),
            ("wParamL", ctypes.c_short),
            ("wParamH", ctypes.c_ushort),
        ]

    class MouseInput(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class Input_I(ctypes.Union):
        _fields_ = [("ki", KeyBdInput), ("mi", MouseInput), ("hi", HardwareInput)]

    class Input(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]
else:
    KeyBdInput = HardwareInput = MouseInput = Input_I = Input = None  # type: ignore


AnyModifier = 1 << 15
GrabModeAsync = 1
KeyPress = 2
GenericEvent = 35
LockMask = 1 << 1
Mod2Mask = 1 << 4
_MOD_COMBOS = (0, LockMask, Mod2Mask, LockMask | Mod2Mask)
XIAllDevices = 0
XI_RawKeyPress = 13
# NumLock off : le pavé envoie KP_Insert au lieu de KP_0, etc.
_KEYPAD_TWINS = {
    "KP_0": "KP_Insert",
    "KP_Insert": "KP_0",
    "KP_1": "KP_End",
    "KP_End": "KP_1",
    "KP_2": "KP_Down",
    "KP_Down": "KP_2",
    "KP_3": "KP_Next",
    "KP_Next": "KP_3",
    "KP_4": "KP_Left",
    "KP_Left": "KP_4",
    "KP_5": "KP_Begin",
    "KP_Begin": "KP_5",
    "KP_6": "KP_Right",
    "KP_Right": "KP_6",
    "KP_7": "KP_Home",
    "KP_Home": "KP_7",
    "KP_8": "KP_Up",
    "KP_Up": "KP_8",
    "KP_9": "KP_Prior",
    "KP_Prior": "KP_9",
    "KP_Decimal": "KP_Delete",
    "KP_Delete": "KP_Decimal",
}


def _lookup_names(keysym: str) -> list[str]:
    """KP_0, KP_Insert et 0 du haut sont la même touche de lancement."""
    names = [keysym]
    twin = _KEYPAD_TWINS.get(keysym)
    if twin:
        names.append(twin)
    if keysym.startswith("KP_") and len(keysym) == 4 and keysym[3].isdigit():
        names.append(keysym[3])
    if len(keysym) == 1 and keysym.isdigit():
        names.append(f"KP_{keysym}")
        twin = _KEYPAD_TWINS.get(f"KP_{keysym}")
        if twin:
            names.append(twin)
    out: list[str] = []
    for name in names:
        if name and name not in out:
            out.append(name)
    return out


class XKeyEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("root", ctypes.c_ulong),
        ("subwindow", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("x_root", ctypes.c_int),
        ("y_root", ctypes.c_int),
        ("state", ctypes.c_uint),
        ("keycode", ctypes.c_uint),
        ("same_screen", ctypes.c_int),
    ]


class XGenericEventCookie(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("extension", ctypes.c_int),
        ("evtype", ctypes.c_int),
        ("cookie", ctypes.c_uint),
        ("data", ctypes.c_void_p),
    ]


class XIRawEventLite(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("extension", ctypes.c_int),
        ("evtype", ctypes.c_int),
        ("time", ctypes.c_ulong),
        ("deviceid", ctypes.c_int),
        ("sourceid", ctypes.c_int),
        ("detail", ctypes.c_int),
    ]


class XIEventMask(ctypes.Structure):
    _fields_ = [
        ("deviceid", ctypes.c_int),
        ("mask_len", ctypes.c_int),
        ("mask", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class XEvent(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_int),
        ("xkey", XKeyEvent),
        ("cookie", XGenericEventCookie),
        ("pad", ctypes.c_long * 24),
    ]


class HotkeyGrabber:
    """Touche de lancement même quand Elite a le focus (XI2 Linux / hook LL Windows)."""

    def __init__(self, on_key) -> None:
        self.on_key = on_key
        self._macros: dict[str, dict] = {}
        self._paused = False
        self._running = False
        self._thread: threading.Thread | None = None
        self._wake_r = None
        self._wake_w = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        if sys.platform == "win32":
            self._thread = threading.Thread(target=self._loop_win, daemon=True, name="macro-hotkeys")
        else:
            self._wake_r, self._wake_w = os.pipe()
            os.set_blocking(self._wake_r, False)
            os.set_blocking(self._wake_w, False)
            self._thread = threading.Thread(target=self._loop_x11, daemon=True, name="macro-hotkeys")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._wake()
        if self._thread is not None:
            self._thread.join(timeout=1.2)
            self._thread = None
        if self._wake_r is not None:
            try:
                os.close(self._wake_r)
                os.close(self._wake_w)
            except OSError:
                pass
            self._wake_r = self._wake_w = None

    def set_macros(self, macros: dict[str, dict]) -> None:
        with self._lock:
            self._macros = dict(macros)
        self._wake()

    def pause(self) -> None:
        self._paused = True
        self._wake()

    def resume(self) -> None:
        self._paused = False
        self._wake()

    def _wake(self) -> None:
        if self._wake_w is None:
            return
        try:
            os.write(self._wake_w, b"\0")
        except OSError:
            pass

    def _fire(self, keysym: str) -> None:
        if self._paused or is_playing():
            return
        with self._lock:
            macros = self._macros
            row = None
            for name in _lookup_names(keysym):
                row = macros.get(name)
                if row:
                    break
        if row and self.on_key:
            self.on_key(row)

    def _names_for_code(self, x11, dpy, keycode: int) -> list[str]:
        names: list[str] = []
        for level in range(4):
            ks = x11.XKeycodeToKeysym(dpy, keycode, level)
            if not ks:
                continue
            raw = x11.XKeysymToString(ks)
            if not raw:
                continue
            name = raw.decode("ascii", "replace")
            if name and name not in names:
                names.append(name)
        return names

    def _fire_code(self, x11, dpy, keycode: int) -> bool:
        for name in self._names_for_code(x11, dpy, keycode):
            with self._lock:
                hit = any(n in self._macros for n in _lookup_names(name))
            if hit:
                self._fire(name)
                return True
        return False

    def _loop_x11(self) -> None:
        """Linux : XI2 raw (Elite a le focus) + XGrabKey en secours."""
        import select
        from ctypes.util import find_library

        libname = find_library("X11")
        if not libname:
            return
        x11 = ctypes.cdll.LoadLibrary(libname)
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XDefaultRootWindow.restype = ctypes.c_ulong
        x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x11.XStringToKeysym.restype = ctypes.c_ulong
        x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
        x11.XKeysymToKeycode.restype = ctypes.c_uint
        x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x11.XKeycodeToKeysym.restype = ctypes.c_ulong
        x11.XKeycodeToKeysym.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int]
        x11.XKeysymToString.restype = ctypes.c_char_p
        x11.XKeysymToString.argtypes = [ctypes.c_ulong]
        x11.XGrabKey.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ]
        x11.XUngrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]
        x11.XPending.argtypes = [ctypes.c_void_p]
        x11.XPending.restype = ctypes.c_int
        x11.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        x11.XConnectionNumber.argtypes = [ctypes.c_void_p]
        x11.XConnectionNumber.restype = ctypes.c_int
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x11.XGetEventData.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        x11.XGetEventData.restype = ctypes.c_int
        x11.XFreeEventData.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        dpy = x11.XOpenDisplay(None)
        if not dpy:
            return
        root = x11.XDefaultRootWindow(dpy)
        fd = x11.XConnectionNumber(dpy)
        grabbed: list[tuple[int, int]] = []
        last_fire = 0.0
        xi_mask_bytes = (ctypes.c_ubyte * 4)()

        def select_raw() -> None:
            xi_name = find_library("Xi") or "libXi.so.6"
            try:
                xi = ctypes.cdll.LoadLibrary(xi_name)
            except OSError:
                return
            xi.XISelectEvents.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int,
            ]
            xi.XISelectEvents.restype = ctypes.c_int
            xi.XIQueryVersion.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ]
            xi.XIQueryVersion.restype = ctypes.c_int
            major = ctypes.c_int(2)
            minor = ctypes.c_int(0)
            if xi.XIQueryVersion(dpy, ctypes.byref(major), ctypes.byref(minor)) != 0:
                return
            xi_mask_bytes[XI_RawKeyPress >> 3] |= 1 << (XI_RawKeyPress & 7)
            evmask = XIEventMask()
            evmask.deviceid = XIAllDevices
            evmask.mask_len = len(xi_mask_bytes)
            evmask.mask = ctypes.cast(xi_mask_bytes, ctypes.POINTER(ctypes.c_ubyte))
            xi.XISelectEvents(dpy, root, ctypes.byref(evmask), 1)
            x11.XFlush(dpy)

        def ungrab() -> None:
            for code, mods in grabbed:
                x11.XUngrabKey(dpy, code, mods, root)
            grabbed.clear()
            x11.XFlush(dpy)

        def grab() -> None:
            ungrab()
            if self._paused:
                return
            with self._lock:
                keys = list(self._macros)
            seen_codes: set[int] = set()
            wanted = []
            for keysym in keys:
                wanted.extend(_lookup_names(keysym))
            for keysym in wanted:
                ks = x11.XStringToKeysym(keysym.encode("ascii", "replace"))
                if not ks:
                    continue
                code = int(x11.XKeysymToKeycode(dpy, ks))
                if not code or code in seen_codes:
                    continue
                seen_codes.add(code)
                for mods in _MOD_COMBOS:
                    x11.XGrabKey(dpy, code, mods, root, 0, GrabModeAsync, GrabModeAsync)
                    grabbed.append((code, mods))
            x11.XFlush(dpy)

        select_raw()
        grab()
        ev = XEvent()
        try:
            while self._running:
                if self._paused and grabbed:
                    ungrab()
                elif (not self._paused) and not grabbed:
                    grab()
                wait = [fd]
                if self._wake_r is not None:
                    wait.append(self._wake_r)
                try:
                    ready, _, _ = select.select(wait, [], [], 0.4)
                except (OSError, ValueError):
                    break
                if self._wake_r in ready:
                    try:
                        os.read(self._wake_r, 64)
                    except OSError:
                        pass
                    grab()
                    continue
                if fd not in ready:
                    continue
                while x11.XPending(dpy):
                    x11.XNextEvent(dpy, ctypes.byref(ev))
                    keycode = 0
                    if ev.type == KeyPress:
                        keycode = int(ev.xkey.keycode)
                    elif ev.type == GenericEvent and ev.cookie.evtype == XI_RawKeyPress:
                        cookie = ctypes.cast(ctypes.byref(ev), ctypes.POINTER(XGenericEventCookie)).contents
                        if x11.XGetEventData(dpy, ctypes.byref(cookie)) and cookie.data:
                            raw = ctypes.cast(cookie.data, ctypes.POINTER(XIRawEventLite)).contents
                            keycode = int(raw.detail)
                            x11.XFreeEventData(dpy, ctypes.byref(cookie))
                        else:
                            continue
                    else:
                        continue
                    now = time.monotonic()
                    if now - last_fire < 0.45:
                        continue
                    if self._fire_code(x11, dpy, keycode):
                        last_fire = now
        finally:
            ungrab()
            x11.XCloseDisplay(dpy)

    def _loop_win(self) -> None:
        """Windows : hook WH_KEYBOARD_LL ; RegisterHotKey si le hook est refusé."""
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        WM_HOTKEY = 0x0312
        WM_QUIT = 0x0012
        WM_KEYDOWN = 0x0100
        WM_SYSKEYDOWN = 0x0104
        WH_KEYBOARD_LL = 13
        LLKHF_INJECTED = 0x10
        ids: dict[int, str] = {}
        last_fire = 0.0

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("message", ctypes.c_uint),
                ("wParam", ctypes.c_ulonglong),
                ("lParam", ctypes.c_ulonglong),
                ("time", ctypes.c_ulong),
                ("pt", POINT),
            ]

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("vkCode", ctypes.c_uint),
                ("scanCode", ctypes.c_uint),
                ("flags", ctypes.c_uint),
                ("time", ctypes.c_uint),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        LRESULT = ctypes.c_ssize_t
        WPARAM = ctypes.c_size_t
        LPARAM = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)

        def vk_map() -> dict[int, str]:
            with self._lock:
                macros = dict(self._macros)
            out: dict[int, str] = {}
            for keysym in macros:
                for name in _lookup_names(keysym):
                    vk = _win_vk(name)
                    if vk is not None:
                        out[vk] = keysym
            return out

        def unreg() -> None:
            for hid in list(ids):
                user32.UnregisterHotKey(None, hid)
            ids.clear()

        def reg() -> None:
            unreg()
            if self._paused:
                return
            hid = 1
            seen: set[int] = set()
            for vk, keysym in vk_map().items():
                if vk in seen:
                    continue
                if user32.RegisterHotKey(None, hid, 0x4000, vk):
                    ids[hid] = keysym
                    seen.add(vk)
                    hid += 1

        def maybe_fire(keysym: str) -> None:
            nonlocal last_fire
            now = time.monotonic()
            if now - last_fire < 0.45:
                return
            last_fire = now
            self._fire(keysym)

        @HOOKPROC
        def hook_cb(ncode, wparam, lparam):
            if ncode >= 0 and not self._paused:
                info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not (info.flags & LLKHF_INJECTED):
                    bound = vk_map()
                    vk = int(info.vkCode)
                    if vk in bound:
                        if int(wparam) in (WM_KEYDOWN, WM_SYSKEYDOWN):
                            maybe_fire(bound[vk])
                        return LRESULT(1)
            return user32.CallNextHookEx(None, ncode, wparam, lparam)

        self._win_hook_cb = hook_cb
        hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, hook_cb, kernel32.GetModuleHandleW(None), 0,
        )
        if not hook:
            reg()
        msg = MSG()
        try:
            while self._running:
                if not hook:
                    if self._paused and ids:
                        unreg()
                    elif (not self._paused) and not ids:
                        reg()
                ret = user32.MsgWaitForMultipleObjects(0, None, False, 200, 0x04FF)
                if ret == 0x0102:
                    continue
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == WM_QUIT:
                        return
                    if msg.message == WM_HOTKEY:
                        keysym = ids.get(int(msg.wParam))
                        if keysym:
                            maybe_fire(keysym)
                    else:
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
                if not hook:
                    with self._lock:
                        wanted = set(self._macros)
                    if wanted != set(ids.values()):
                        reg()
        finally:
            if hook:
                user32.UnhookWindowsHookEx(hook)
            unreg()
            self._win_hook_cb = None


def hotkey_in_use(keysym: str, *, except_id: str | None = None) -> bool:
    """True si une autre macro a déjà cette touche (pavé et rangée du haut = même)."""
    keysym = (keysym or "").strip()
    if not keysym:
        return False
    aliases = set(_lookup_names(keysym))
    for row in load_macros():
        if except_id and row.get("id") == except_id:
            continue
        bound = (row.get("hotkey") or "").strip()
        if bound and (bound in aliases or set(_lookup_names(bound)) & aliases):
            return True
    return False


def binds_map() -> dict[str, dict]:
    """Touche de lancement → macro, pour le grabber."""
    out: dict[str, dict] = {}
    for row in load_macros():
        key = (row.get("hotkey") or "").strip()
        if key:
            out[key] = row
    return out
