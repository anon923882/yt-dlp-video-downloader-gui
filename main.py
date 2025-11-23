"""
Professional, modular CLI for YT-DLP video downloading with light, readable coloring, configurable parallel downloads, and an always-visible status panel.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple
import yt_dlp
# ============== UI AND COLOR ==============
class Palette:
    HEADER   = "\033[38;5;153m"
    ACCENT   = "\033[38;5;215m"
    SUCCESS  = "\033[38;5;40m"
    WARNING  = "\033[38;5;214m"
    ERROR    = "\033[38;5;203m"
    SYSTEM   = "\033[38;5;252m"
    VALUE    = "\033[38;5;51m"
    CODE     = "\033[38;5;39m"
    INFO     = "\033[38;5;81m"
    BOLD     = "\033[1m"
    RESET    = "\033[0m"
# Coloring helpers

def style(text: str, color: str) -> str:
    return f"{color}{text}{Palette.RESET}" if supports_ansi() else text

def status_text(val: bool) -> str:
    return style("ON", Palette.SUCCESS) if val else style("OFF", Palette.WARNING)

def value_text(text: str) -> str:
    return style(text, Palette.VALUE)

def accent(text: str) -> str:
    return style(text, Palette.ACCENT)

def header(text: str) -> None:
    print(style(text, Palette.HEADER + Palette.BOLD))

def code_text(text: str) -> str:
    return style(text, Palette.CODE)

def info_text(text: str) -> str:
    return style(text, Palette.INFO)

def warning_text(text: str) -> str:
    return style(text, Palette.WARNING)

def error_text(text: str) -> str:
    return style(text, Palette.ERROR)

def clear_console() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')

def prompt(text: str) -> str:
    return style(f"{text}: ", Palette.ACCENT + Palette.BOLD)

def supports_ansi() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text)
# ============= CURSOR/MENU RENDERING =============
_CURSOR_HIDE_DEPTH = 0

def push_hidden_cursor() -> None:
    global _CURSOR_HIDE_DEPTH
    if _CURSOR_HIDE_DEPTH == 0:
        hide_cursor()
    _CURSOR_HIDE_DEPTH += 1

def pop_hidden_cursor(force: bool = False) -> None:
    global _CURSOR_HIDE_DEPTH
    if force:
        _CURSOR_HIDE_DEPTH = 0
        show_cursor()
    elif _CURSOR_HIDE_DEPTH > 0:
        _CURSOR_HIDE_DEPTH -= 1
        if _CURSOR_HIDE_DEPTH == 0:
            show_cursor()

def is_cursor_hidden() -> bool:
    return _CURSOR_HIDE_DEPTH > 0

def hide_cursor() -> bool:
    if supports_ansi():
        try:
            sys.stdout.write("\x1b[?25l")
            sys.stdout.flush()
            return True
        except Exception:
            pass
    return False

def show_cursor() -> bool:
    if supports_ansi():
        try:
            sys.stdout.write("\x1b[?25h")
            sys.stdout.flush()
            return True
        except Exception:
            pass
    return False
class MenuScreen:
    def __init__(self):
        self._display_lines = 0
        self._initial = True
        self._supports_cursor = supports_ansi()
        self._cursor_managed = False
    def __enter__(self):
        self._ensure_cursor_hidden()
        return self
    def __exit__(self, exc_type, exc, tb):
        self.close()
    def render(self, lines: List[str]):
        self._ensure_cursor_hidden()
        shown = self._measure_display_lines(lines)
        if self._initial:
            clear_console()
            self._initial = False
        elif self._supports_cursor and self._display_lines:
            sys.stdout.write(f"\x1b[{self._display_lines}F\x1b[J")
        else:
            clear_console()
        print("\n".join(lines))
        self._display_lines = shown
    def reset(self):
        self._display_lines = 0
        self._initial = True
    def close(self):
        if self._cursor_managed: pop_hidden_cursor()
        self._cursor_managed = False
        self.reset()
    def _ensure_cursor_hidden(self):
        if not self._cursor_managed: push_hidden_cursor(); self._cursor_managed = True
        elif not is_cursor_hidden(): push_hidden_cursor()
    def _measure_display_lines(self, lines: List[str]) -> int:
        try:
            width = shutil.get_terminal_size(fallback=(80,24)).columns
        except Exception:
            width = 80
        total = 0
        width = max(1, width)
        for entry in lines:
            plain = strip_ansi(entry)
            total += max(1, (len(plain) + width - 1) // width) if plain else 1
        return total
# ============= SETTINGS AND STATUS =============
SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"

@dataclass
class RuntimeSettings:
    OutputFolder: Path = Path("downloads")
    OverwriteExisting: bool = False
    ParallelDownloads: int = 4
    RetryAttempts: int = 2
    ChunkSizeKiB: int = 512
    ShowStatusPanel: bool = True
    SettingsPath: Path = field(default=SETTINGS_PATH, init=False, repr=False)
    def __post_init__(self): self.refresh_paths()
    def refresh_paths(self): self.OutputFolder = self.OutputFolder.expanduser()
    def to_payload(self) -> Dict[str, object]:
        return {"OutputFolder": str(self.OutputFolder), "OverwriteExisting": self.OverwriteExisting, "ParallelDownloads": self.ParallelDownloads, "RetryAttempts": self.RetryAttempts, "ChunkSizeKiB": self.ChunkSizeKiB, "ShowStatusPanel": self.ShowStatusPanel}
    def save(self):
        self.SettingsPath.parent.mkdir(parents=True, exist_ok=True)
        with self.SettingsPath.open("w", encoding="utf-8") as h:
            json.dump(self.to_payload(), h, indent=2)
    @classmethod
    def load(cls) -> "RuntimeSettings":
        instance = cls()
        if not instance.SettingsPath.exists(): return instance
        try:
            payload = json.loads(instance.SettingsPath.read_text(encoding="utf-8"))
        except Exception:
            return instance
        if isinstance(payload, dict):
            for f in ["OutputFolder", "OverwriteExisting", "ParallelDownloads", "RetryAttempts", "ChunkSizeKiB", "ShowStatusPanel"]:
                v = payload.get(f)
                if v is not None:
                    setattr(instance, f, v if f != "OutputFolder" else Path(v))
        instance.refresh_paths()
        return instance
# ----------- STATUS PANEL -----------
def format_size(sz: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    val = float(sz)
    for i, unit in enumerate(units):
        if val < 1024 or i==len(units)-1:
            return f"{int(val)} {unit}" if unit=="B" else f"{val:.2f} {unit}"
        val /= 1024

def status_panel(settings: RuntimeSettings) -> List[str]:
    return [
        style("YT-DLP CLI STATUS", Palette.HEADER),
        f" {accent('Output folder').ljust(15)} {info_text(str(settings.OutputFolder))}",
        f" {accent('Overwrite').ljust(15)} {status_text(settings.OverwriteExisting)}",
        f" {accent('Parallel').ljust(15)} {value_text(str(settings.ParallelDownloads))}",
        f" {accent('Retries').ljust(15)} {value_text(str(settings.RetryAttempts))}",
        f" {accent('Chunk (KiB)').ljust(15)} {value_text(str(settings.ChunkSizeKiB))}",
        f" {accent('Show Status').ljust(15)} {status_text(settings.ShowStatusPanel)}",
        ""
    ] if settings.ShowStatusPanel else []
# ============= MENUS =============
def format_menu_option(label: str, value: str = "", hint: str = "", selected: bool = False) -> str:
    marker = style("›", Palette.ACCENT) if selected else " "
    label_styled = style(label, Palette.ACCENT + Palette.BOLD) if selected else label
    val_col = Palette.SUCCESS if value in ["ON", "on", "ENABLED"] else Palette.WARNING if value in ["OFF", "off", "DISABLED"] else Palette.VALUE
    parts = [f"{marker} {label_styled}"]
    if value:
        parts.append(style(f"{value}", val_col))
    if hint:
        parts.append(style(f"({hint})", Palette.WARNING))
    return " ".join(parts)
def supports_keyboard_navigation() -> bool:
    try:
        import msvcrt
        return True
    except ImportError:
        try:
            import tty, termios
            return sys.stdin.isatty()
        except ImportError:
            return False

def read_keypress() -> str:
    try:
        import msvcrt
        while msvcrt.kbhit(): msvcrt.getch()
        key = msvcrt.getch()
        if key in (b'\x00', b'\xe0'):
            k = msvcrt.getch()
            return "UP" if k==b'H' else "DOWN" if k==b'P' else ""
        elif key == b'\r': return "ENTER"
        elif key == b' ': return "SPACE"
        elif key == b'\x1b': return "ESC"
    except ImportError:
        import tty, termios, select
        fd = sys.stdin.fileno()
        orig = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch in {'\r','\n'}: return "ENTER"
            if ch == '\x1b':
                ready,_,_ = select.select([sys.stdin],[],[],0.05)
                if not ready: return "ESC"
                next = sys.stdin.read(1)
                if next == '[':
                    arr = sys.stdin.read(1)
                    return "UP" if arr=='A' else "DOWN" if arr=='B' else ""
                return next
            if ch == ' ': return "SPACE"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, orig)
    return ""
# ============= DOWNLOAD AND FORMAT LOGIC =============
def fetch_formats(url: str) -> Tuple[Optional[dict], Optional[List[dict]], Optional[str]]:
    try:
        with yt_dlp.YoutubeDL({'quiet':True,'no_warnings':True}) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = [
                {
                    'format_id': f.get('format_id'),
                    'height': f.get('height', 0),
                    'ext': f.get('ext', 'N/A'),
                    'filesize': f.get('filesize', 0),
                    'fps': f.get('fps', 'N/A')
                }
                for f in info.get('formats', []) if f.get('vcodec') != 'none' and f.get('acodec') != 'none']
            return info, formats, None
    except Exception as e:
        return None, None, str(e)

def download_job(url:str, format_id:str, out_path:Path, progress:ProgressDisplay, tries:int=1) -> Tuple[bool, Optional[str]]:
    last_exception = None
    for attempt in range(1,tries+1):
        try:
            def progress_hook(d):
                if d['status']=='downloading':
                    filename = Path(d.get('filename','video')).name
                    percent = d.get('_percent_str', 'N/A').strip()
                    speed = d.get('_speed_str', 'N/A').strip()
                    progress.update(filename, percent, speed)
                elif d['status']=='finished':
                    filename = Path(d.get('filename','video')).name
                    progress.complete(filename, True)
            opts = {'format':format_id,'outtmpl':str(out_path/'%(title)s.%(ext)s'),'progress_hooks':[progress_hook],'quiet':True}
            with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([url])
            return True, None
        except Exception as exc:
            last_exception = exc
    return False,str(last_exception)

class ProgressDisplay:
    def __init__(self):
        self._current_file = ''
        self._lock = Lock()
        self._last_update = 0.0
    def update(self, filename:str, percent:str, speed:str):
        now = time.time()
        if now-self._last_update<0.5: return
        self._last_update = now
        with self._lock:
            if filename != self._current_file:
                self._current_file = filename
                print(f"\n{style('[Download]',Palette.INFO)} {code_text(filename)}")
            print(f"\rProgress: {value_text(percent)} | Speed: {value_text(speed)}", end='', flush=True)
    def complete(self, filename:str,success:bool):
        with self._lock:
            status = style('✓ Done', Palette.SUCCESS) if success else style('✗ Failed', Palette.ERROR)
            print(f"\r{style('[Download]',Palette.INFO)} {code_text(filename)}: {status}")
# ============= MENU/CONTROL =============
def select_format(formats: List[dict]) -> Optional[dict]:
    if not formats: return None
    selection = 0
    navigation_hint = style("Use ↑/↓ to navigate, Enter to select, ESC to cancel.", Palette.ACCENT)
    with MenuScreen() as screen:
        while True:
            lines = [style("Select Format", Palette.HEADER)]
            for idx, fmt in enumerate(formats):
                h=fmt['height']; ext=fmt['ext']; sz=format_size(fmt['filesize']) if fmt['filesize'] else 'Unknown size'; fps=fmt['fps']
                label = f"{h}p"; value = f"{ext} | {sz} | {fps} fps"
                lines.append(format_menu_option(label, value=value, selected=selection==idx))
            lines.append(""); lines.append(navigation_hint);screen.render(lines)
            k = read_keypress()
            if k=="UP": selection = (selection-1)%len(formats)
            elif k=="DOWN": selection=(selection+1)%len(formats)
            elif k=="ENTER": screen.reset(); return formats[selection]
            elif k=="ESC": screen.reset(); return None

def handle_download(settings: RuntimeSettings):
    clear_console(); pop_hidden_cursor(force=True)
    lines = status_panel(settings)
    if lines: print("\n".join(lines))
    header("Download Video")
    url = input(prompt("Enter video URL")).strip()
    if not url:
        print(warning_text("No URL provided")); input(prompt("Press Enter to continue")); return
    print(info_text("Fetching formats..."))
    info, formats, error = fetch_formats(url)
    if error:
        print(error_text(f"Error: {error}")); input(prompt("Press Enter to continue")); return
    if not formats:
        print(warning_text("No combined video+audio formats found")); input(prompt("Press Enter to continue")); return
    formats.sort(key=lambda x:x['height'],reverse=True)
    selected = select_format(formats)
    if not selected:
        print(info_text("Download cancelled")); input(prompt("Press Enter to continue")); return
    clear_console(); lines = status_panel(settings)
    if lines: print("\n".join(lines))
    header("Download Summary")
    print(f" Title: {value_text(info.get('title','Unknown'))}\n Quality: {value_text(str(selected['height'])+'p')}\n Format: {value_text(selected['ext'])}\n Size: {value_text(format_size(selected['filesize']) if selected['filesize'] else 'Unknown')}\n Destination: {info_text(str(settings.OutputFolder))}")
    if input(prompt("Start download? (y/n)")).strip().lower() != 'y':
        print(warning_text("Download cancelled")); input(prompt("Press Enter to continue")); return
    settings.OutputFolder.mkdir(parents=True, exist_ok=True)
    print(info_text("Starting download..."))
    progress = ProgressDisplay()
    result_errs = []
    with ThreadPoolExecutor(max_workers=settings.ParallelDownloads) as pool:
        futs = [ pool.submit(download_job, url, selected['format_id'], settings.OutputFolder, progress, settings.RetryAttempts) ]
        for fut in as_completed(futs):
            success, err = fut.result()
            if not success: result_errs.append(err)
    print(success_text("Download completed!" if not result_errs else "Some downloads failed"))
    if result_errs:
        for e in result_errs:
            print(error_text(str(e)))
    input(prompt("Press Enter to continue"))

def configure_settings(settings: RuntimeSettings):
    selection = 0
    def build_options() -> list[dict]:
        return [
            {"label": "Output folder", "value": str(settings.OutputFolder), "action": "output"},
            {"label": "Overwrite", "value": "ON" if settings.OverwriteExisting else "OFF", "action": "overwrite"},
            {"label": "Parallel dl", "value": str(settings.ParallelDownloads), "action": "parallel"},
            {"label": "Retries", "value": str(settings.RetryAttempts), "action": "retries"},
            {"label": "Chunk KiB", "value": str(settings.ChunkSizeKiB), "action": "chunk"},
            {"label": "Status panel", "value": "ON" if settings.ShowStatusPanel else "OFF", "action": "status"},
            {"label": "Back", "hint": "main menu", "action": "back"},
        ]
    navigation_hint = style("Use ↑/↓ to navigate, Enter to select.", Palette.ACCENT)
    with MenuScreen() as screen:
        while True:
            opts = build_options()
            selection = min(selection, len(opts)-1)
            lines = status_panel(settings) + [style("Settings",Palette.HEADER)]
            for idx, o in enumerate(opts):
                lines.append(format_menu_option(o['label'], value=o.get('value',''), hint=o.get('hint',''), selected=selection==idx))
            lines.append(""); lines.append(navigation_hint); screen.render(lines); k=read_keypress()
            if k=="UP": selection = (selection - 1) % len(opts)
            elif k=="DOWN": selection = (selection + 1) % len(opts)
            elif k=="ENTER":
                c=opts[selection]['action']; screen.reset(); clear_console(); pop_hidden_cursor(force=True)
                if c=="output":
                    p=input(prompt("New output folder")).strip();
                    if p: settings.OutputFolder=Path(p); settings.refresh_paths(); settings.save(); print(success_text("Output folder updated"))
                    else: print(warning_text("No folder provided"))
                    input(prompt("Press Enter to continue"))
                elif c=="overwrite":
                    settings.OverwriteExisting = not settings.OverwriteExisting;settings.save(); print(success_text("Overwrite toggled")); input(prompt("Press Enter to continue"))
                elif c=="parallel":
                    v=input(prompt("Parallel downloads (1-16)")).strip();
                    if v.isdigit():settings.ParallelDownloads=max(1,min(16,int(v)));settings.save(); print(success_text(f"Parallel set to {settings.ParallelDownloads}"))
                    else: print(warning_text("Invalid number")); input(prompt("Press Enter to continue"))
                elif c=="retries":
                    v=input(prompt("Retries (0-10)")).strip();
                    if v.isdigit():settings.RetryAttempts=max(0,min(10,int(v)));settings.save(); print(success_text(f"Retries set to {settings.RetryAttempts}"))
                    else: print(warning_text("Invalid number")); input(prompt("Press Enter to continue"))
                elif c=="chunk":
                    v=input(prompt("Chunk size in KiB (64-4096)")).strip();
                    if v.isdigit():settings.ChunkSizeKiB=max(64,min(4096,int(v)));settings.save(); print(success_text("Chunk size updated"))
                    else: print(warning_text("Invalid number")); input(prompt("Press Enter to continue"))
                elif c=="status":
                    settings.ShowStatusPanel = not settings.ShowStatusPanel; settings.save(); print(success_text("Status panel toggled")); input(prompt("Press Enter to continue"))
                elif c=="back": break
                screen.reset()
def main():
    settings = RuntimeSettings.load()
    if not supports_keyboard_navigation():
        print(error_text("Keyboard navigation required. Run in interactive terminal.")); return
    selection = 0
    def build_options() -> list[dict]:
        return [
            {"label": "Download video", "action": "download"},
            {"label": "Settings", "action": "settings"},
            {"label": "Exit", "action": "exit"},
        ]
    navigation_hint = style("Use ↑/↓ to navigate, Enter to select.", Palette.ACCENT)
    with MenuScreen() as screen:
        while True:
            opts = build_options()
            selection = min(selection, len(opts)-1)
            lines = status_panel(settings) + [style("YT-DLP Video Downloader", Palette.HEADER+Palette.BOLD), "", style("Menu", Palette.HEADER)]
            for idx, o in enumerate(opts):
                lines.append(format_menu_option(o['label'], selected=selection==idx))
            lines.append(""); lines.append(navigation_hint); screen.render(lines); k=read_keypress()
            if k=="UP": selection = (selection - 1) % len(opts)
            elif k=="DOWN": selection = (selection + 1) % len(opts)
            elif k=="ENTER":
                c=opts[selection]['action']; screen.reset(); clear_console();
                if c=="download": handle_download(settings)
                elif c=="settings": configure_settings(settings)
                elif c=="exit": print(success_text("Goodbye!")); break
                screen.reset()
    clear_console()
if __name__ == "__main__":
    main()
