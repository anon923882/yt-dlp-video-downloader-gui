"""
YT-DLP Video Downloader CLI
Modular, interactive CLI for downloading videos with format selection
"""
from __future__ import annotations
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import yt_dlp
# ====== UI MODULE ======
class Palette:
    HEADER = "\x1b[1;36m"
    ACCENT = "\x1b[33m"
    SUCCESS = "\x1b[32m"
    WARNING = "\x1b[33m"
    ERROR = "\x1b[31m"
    SYSTEM = "\x1b[90m"
    VALUE = "\x1b[35m"
    CODE = "\x1b[36m"
    RESET = "\x1b[0m"
    BOLD = "\x1b[1m"
def supports_ansi() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
def style(text: str, color: str) -> str:
    if not supports_ansi():
        return text
    return f"{color}{text}{Palette.RESET}"
def header(text: str) -> None:
    print(style(f"\n{'=' * 60}", Palette.HEADER))
    print(style(text, Palette.HEADER + Palette.BOLD))
    print(style('=' * 60, Palette.HEADER))
def success_text(text: str) -> str:
    return style(text, Palette.SUCCESS)
def error_text(text: str) -> str:
    return style(text, Palette.ERROR)
def warning_text(text: str) -> str:
    return style(text, Palette.WARNING)
def accent(text: str) -> str:
    return style(text, Palette.ACCENT)
def value_text(text: str) -> str:
    return style(text, Palette.VALUE)
def code_text(text: str) -> str:
    return style(text, Palette.CODE)
def system_message(text: str, tone: str = "system") -> None:
    colors = {"success": Palette.SUCCESS, "error": Palette.ERROR, "warning": Palette.WARNING, "system": Palette.SYSTEM}
    print(style(f"[{tone.upper()}] {text}", colors.get(tone, Palette.SYSTEM)))
def prompt(text: str) -> str:
    return style(f"{text}: ", Palette.ACCENT + Palette.BOLD)
def format_label_value(label: str, value: str, coloured: bool = False) -> str:
    label_styled = style(f"{label}:", Palette.SYSTEM)
    value_display = value if coloured else style(value, Palette.VALUE)
    return f"{label_styled} {value_display}"
def clear_console() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')
def format_menu_option(label: str, value: str = "", hint: str = "", selected: bool = False) -> str:
    marker = "►" if selected else " "
    marker_styled = style(marker, Palette.ACCENT)
    if selected:
        label_styled = style(label, Palette.ACCENT + Palette.BOLD)
    else:
        label_styled = label
    parts = [f"{marker_styled} {label_styled}"]
    if value:
        value_styled = style(f"[{value}]", Palette.VALUE)
        parts.append(value_styled)
    if hint:
        hint_styled = style(f"({hint})", Palette.SYSTEM)
        parts.append(hint_styled)
    return " ".join(parts)
def supports_keyboard_navigation() -> bool:
    try:
        import msvcrt
        return True
    except ImportError:
        pass
    try:
        import tty
        import termios
        return sys.stdin.isatty()
    except ImportError:
        return False
def read_keypress() -> str:
    # Get single keypress from user (Win/nix)
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
        key = msvcrt.getch()
        if key in (b'\x00', b'\xe0'):
            key = msvcrt.getch()
            if key == b'H': return "UP"
            elif key == b'P': return "DOWN"
        elif key == b'\r': return "ENTER"
        elif key == b' ': return "SPACE"
        elif key == b'\x1b': return "ESC"
    except ImportError:
        import tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A': return "UP"
                    elif ch3 == 'B': return "DOWN"
                return "ESC"
            elif ch == '\r' or ch == '\n': return "ENTER"
            elif ch == ' ': return "SPACE"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ""
class MenuScreen:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def render(self, lines: List[str]) -> None:
        clear_console()
        for line in lines: print(line)
    def reset(self) -> None:
        clear_console()
SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"
@dataclass
class RuntimeSettings:
    OutputFolder: Path = Path("downloads")
    OverwriteExisting: bool = False
    ChunkSizeKiB: int = 512
    SettingsPath: Path = field(default=SETTINGS_PATH, init=False, repr=False)
    def __post_init__(self) -> None:
        self.refresh_paths()
    def refresh_paths(self) -> None:
        self.OutputFolder = self.OutputFolder.expanduser()
    def to_payload(self) -> Dict[str, object]:
        return {
            "OutputFolder": str(self.OutputFolder),
            "OverwriteExisting": self.OverwriteExisting,
            "ChunkSizeKiB": self.ChunkSizeKiB,
        }
    def save(self) -> None:
        self.SettingsPath.parent.mkdir(parents=True, exist_ok=True)
        with self.SettingsPath.open("w", encoding="utf-8") as handle:
            json.dump(self.to_payload(), handle, ensure_ascii=False, indent=2)
    @classmethod
    def load(cls) -> "RuntimeSettings":
        instance = cls()
        if not instance.SettingsPath.exists():
            return instance
        try:
            payload = json.loads(instance.SettingsPath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return instance
        if isinstance(payload, dict):
            output_folder = payload.get("OutputFolder")
            if isinstance(output_folder, str) and output_folder.strip():
                instance.OutputFolder = Path(output_folder)
            instance.OverwriteExisting = bool(payload.get("OverwriteExisting", instance.OverwriteExisting))
            chunk_size = payload.get("ChunkSizeKiB")
            if isinstance(chunk_size, int) and chunk_size >= 64:
                instance.ChunkSizeKiB = min(chunk_size, 4096)
        instance.refresh_paths()
        return instance
# ====== PROGRESS DISPLAY ======
def format_size(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size)
    for index, unit in enumerate(units):
        if value < 1024 or index == len(units) - 1:
            if unit == "B": return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TiB"
class ProgressDisplay:
    def __init__(self) -> None:
        self._current_file = ""
        self._last_update = 0.0
    def update(self, filename: str, percent: str, speed: str) -> None:
        now = time.time()
        if now - self._last_update < 0.5: return
        self._last_update = now
        if filename != self._current_file:
            self._current_file = filename
            print(f"\n{style('[Download]', Palette.SYSTEM)} {code_text(filename)}")
        progress_text = f"Progress: {value_text(percent)} | Speed: {value_text(speed)}"
        print(f"\r{progress_text}", end="", flush=True)
    def complete(self, filename: str, success: bool) -> None:
        status = success_text("✓ Complete") if success else error_text("✗ Failed")
        print(f"\r{style('[Download]', Palette.SYSTEM)} {code_text(filename)}: {status}")
# ====== VIDEO FORMATS ======
def fetch_formats(url: str) -> Tuple[Optional[dict], Optional[List[dict]], Optional[str]]:
    try:
        ydl_opts = { 'quiet': True, 'no_warnings': True }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = []
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    formats.append({
                        'format_id': f.get('format_id'),
                        'height': f.get('height', 0),
                        'ext': f.get('ext', 'N/A'),
                        'filesize': f.get('filesize', 0),
                        'fps': f.get('fps', 'N/A'),
                    })
            return info, formats, None
    except Exception as e:
        return None, None, str(e)
def download_video(url: str, format_id: str, output_path: Path, progress: ProgressDisplay) -> Tuple[bool, Optional[str]]:
    try:
        def progress_hook(d):
            if d['status'] == 'downloading':
                filename = Path(d.get('filename', 'video')).name
                percent = d.get('_percent_str', 'N/A').strip()
                speed = d.get('_speed_str', 'N/A').strip()
                progress.update(filename, percent, speed)
            elif d['status'] == 'finished':
                filename = Path(d.get('filename', 'video')).name
                progress.complete(filename, True)
        ydl_opts = {
            'format': format_id,
            'outtmpl': str(output_path / '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'quiet': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True, None
    except Exception as e:
        return False, str(e)
def select_format(formats: List[dict]) -> Optional[dict]:
    if not formats: return None
    selection = 0
    navigation_hint = style("Use ↑/↓ to navigate, Enter to select, ESC to cancel.", Palette.ACCENT)
    with MenuScreen() as screen:
        while True:
            lines = [style("Select Format", Palette.HEADER)]
            for index, fmt in enumerate(formats):
                height = fmt['height']
                ext = fmt['ext']
                size = format_size(fmt['filesize']) if fmt['filesize'] else "Unknown size"
                fps = fmt['fps']
                label = f"{height}p"
                value = f"{ext} | {size} | {fps} fps"
                lines.append(format_menu_option(label, value=value, selected=selection == index))
            lines.append("")
            lines.append(navigation_hint)
            screen.render(lines)
            key = read_keypress()
            if key == "UP":
                selection = (selection - 1) % len(formats)
            elif key == "DOWN":
                selection = (selection + 1) % len(formats)
            elif key == "ENTER":
                screen.reset()
                return formats[selection]
            elif key == "ESC":
                screen.reset()
                return None
def handle_download(settings: RuntimeSettings) -> None:
    clear_console()
    header("Download Video")
    url = input(prompt("Enter video URL")).strip()
    if not url:
        system_message("No URL provided", tone="warning")
        input(prompt("\nPress Enter to continue"))
        return
    system_message("Fetching formats...", tone="system")
    info, formats, error = fetch_formats(url)
    if error:
        system_message(f"Error: {error}", tone="error")
        input(prompt("\nPress Enter to continue"))
        return
    if not formats:
        system_message("No video+audio formats found", tone="warning")
        input(prompt("\nPress Enter to continue"))
        return
    formats.sort(key=lambda x: x['height'], reverse=True)
    selected = select_format(formats)
    if not selected:
        system_message("Download cancelled", tone="warning")
        input(prompt("\nPress Enter to continue"))
        return
    clear_console()
    header("Download Summary")
    print(format_label_value("Title", info.get('title', 'Unknown')))
    print(format_label_value("Quality", f"{selected['height']}p"))
    print(format_label_value("Format", selected['ext']))
    print(format_label_value("Size", format_size(selected['filesize']) if selected['filesize'] else "Unknown"))
    print(format_label_value("Destination", str(settings.OutputFolder)))
    print()
    confirm = input(prompt("Start download? (y/n)")).strip().lower()
    if confirm != 'y':
        system_message("Download cancelled", tone="warning")
        input(prompt("\nPress Enter to continue"))
        return
    settings.OutputFolder.mkdir(parents=True, exist_ok=True)
    print()
    system_message("Starting download...", tone="success")
    progress = ProgressDisplay()
    success, error = download_video(url, selected['format_id'], settings.OutputFolder, progress)
    print()
    if success:
        system_message("Download completed successfully!", tone="success")
    else:
        system_message(f"Download failed: {error}", tone="error")
    input(prompt("\nPress Enter to continue"))
def configure_settings(settings: RuntimeSettings) -> None:
    if not supports_keyboard_navigation():
        system_message("Keyboard navigation required", tone="error")
        input(prompt("Press Enter to continue"))
        return
    selection = 0
    navigation_hint = style("Use ↑/↓ to navigate, Enter to select.", Palette.ACCENT)
    def build_options() -> list[dict]:
        return [
            {"label": "Output folder", "value": str(settings.OutputFolder), "action": "output"},
            {"label": "Overwrite existing", "value": "On" if settings.OverwriteExisting else "Off", "action": "overwrite"},
            {"label": "Chunk size", "value": f"{settings.ChunkSizeKiB} KiB", "action": "chunk"},
            {"label": "Back", "hint": "main menu", "action": "back"},
        ]
    with MenuScreen() as screen:
        while True:
            options = build_options()
            selection = min(selection, len(options) - 1)
            lines = [style("Settings", Palette.HEADER)]
            for index, option in enumerate(options):
                lines.append(format_menu_option(
                    option["label"],
                    value=option.get("value", ""),
                    hint=option.get("hint", ""),
                    selected=selection == index,
                ))
            lines.append("")
            lines.append(navigation_hint)
            screen.render(lines)
            key = read_keypress()
            if key == "UP":
                selection = (selection - 1) % len(options)
            elif key == "DOWN":
                selection = (selection + 1) % len(options)
            elif key == "ENTER":
                choice = options[selection]["action"]
                screen.reset()
                clear_console()
                if choice == "output":
                    new_path = input(prompt("New output folder")).strip()
                    if new_path:
                        settings.OutputFolder = Path(new_path)
                        settings.refresh_paths()
                        settings.save()
                        system_message("Output folder updated", tone="success")
                    else:
                        system_message("No folder provided", tone="warning")
                    input(prompt("\nPress Enter to continue"))
                elif choice == "overwrite":
                    settings.OverwriteExisting = not settings.OverwriteExisting
                    settings.save()
                    state = "enabled" if settings.OverwriteExisting else "disabled"
                    system_message(f"Overwrite {state}", tone="success" if settings.OverwriteExisting else "warning")
                    input(prompt("\nPress Enter to continue"))
                elif choice == "chunk":
                    value = input(prompt("Chunk size in KiB (64-4096)")).strip()
                    if value.isdigit():
                        parsed = int(value)
                        if 64 <= parsed <= 4096:
                            settings.ChunkSizeKiB = parsed
                            settings.save()
                            system_message("Chunk size updated", tone="success")
                        else:
                            system_message("Value out of range", tone="error")
                    else:
                        system_message("Please enter a number", tone="error")
                    input(prompt("\nPress Enter to continue"))
                elif choice == "back":
                    break
                screen.reset()
def main() -> None:
    settings = RuntimeSettings.load()
    if not supports_keyboard_navigation():
        system_message("Keyboard navigation required. Run in an interactive terminal.", tone="error")
        return
    selection = 0
    navigation_hint = style("Use ↑/↓ to navigate, Enter to select.", Palette.ACCENT)
    def build_options() -> list[dict]:
        return [
            {"label": "Download video", "action": "download"},
            {"label": "Settings", "action": "settings"},
            {"label": "Exit", "action": "exit"},
        ]
    with MenuScreen() as screen:
        while True:
            options = build_options()
            selection = min(selection, len(options) - 1)
            lines = [
                style("YT-DLP Video Downloader", Palette.HEADER + Palette.BOLD),
                "",
                format_label_value("Output", str(settings.OutputFolder)),
                format_label_value("Overwrite", "On" if settings.OverwriteExisting else "Off", coloured=True),
                "",
                style("Menu", Palette.HEADER),
            ]
            for index, option in enumerate(options):
                lines.append(format_menu_option(
                    option["label"],
                    selected=selection == index,
                ))
            lines.append("")
            lines.append(navigation_hint)
            screen.render(lines)
            key = read_keypress()
            if key == "UP":
                selection = (selection - 1) % len(options)
            elif key == "DOWN":
                selection = (selection + 1) % len(options)
            elif key == "ENTER":
                choice = options[selection]["action"]
                screen.reset()
                clear_console()
                if choice == "download":
                    handle_download(settings)
                elif choice == "settings":
                    configure_settings(settings)
                elif choice == "exit":
                    system_message("Goodbye!", tone="success")
                    break
                screen.reset()
    clear_console()
if __name__ == "__main__":
    main()
