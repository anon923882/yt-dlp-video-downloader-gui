"""
YT-DLP Video Downloader CLI
Modular, modern, and clear CLI with real parallel download, status panel, and adjustable light palette
"""
from __future__ import annotations
import json
import os
import re
import shutil
import sys
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import yt_dlp
# COLOR PALETTE
class Palette:
    MAIN = "\033[38;5;81m"          # blue
    HEADER = "\033[38;5;117m"        # light cyan
    ACCENT = "\033[38;5;223m"        # pastel yellow
    SUCCESS = "\033[38;5;120m"       # light green
    WARNING = "\033[38;5;208m"       # orange
    ERROR = "\033[38;5;203m"         # salmon red
    SYSTEM = "\033[38;5;149m"        # light purple
    VALUE = "\033[38;5;153m"         # cyan light
    CODE = "\033[38;5;51m"           # strong blue
    RESET = "\033[0m"
    BOLD = "\033[1m"
    INPUT = "\033[38;5;229m"         # cream
# UI HELPERS
def style(text: str, color: str) -> str:
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty(): return text
    return f"{color}{text}{Palette.RESET}"
def accent(text: str) -> str: return style(text, Palette.ACCENT)
def value_text(text: str) -> str: return style(text, Palette.VALUE)
def success_text(text: str) -> str: return style(text, Palette.SUCCESS)
def warning_text(text: str) -> str: return style(text, Palette.WARNING)
def error_text(text: str) -> str: return style(text, Palette.ERROR)
def code_text(text: str) -> str: return style(text, Palette.CODE)
def header(text: str) -> None:
    print(style(f"{'=' * 60}", Palette.HEADER))
    print(style("YT-DLP Video Downloader", Palette.HEADER + Palette.BOLD))
    print(style('=' * 60, Palette.HEADER))
def format_label_value(label: str, value: str, enabled: Optional[bool] = None) -> str:
    label_formatted = accent(label.ljust(20))
    if enabled is None:
        display = value_text(value)
    elif enabled:
        display = success_text(value)
    else:
        display = warning_text(value)
    return f"{label_formatted} {display}"
def prompt(text: str) -> str: return style(f"{text}: ", Palette.INPUT + Palette.BOLD)
def clear_console() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')
# SETTINGS
def bool_label(val: bool) -> Tuple[str, bool]:
    return ("On" if val else "Off", val)
def status_panel(settings: 'RuntimeSettings') -> List[str]:
    # Show main status panel
    return [
        format_label_value("Output Folder", str(settings.OutputFolder)),
        format_label_value("Overwrite", *bool_label(settings.OverwriteExisting)),
        format_label_value("Parallel", str(settings.ParallelDownloads), enabled=settings.ParallelDownloads>1),
        format_label_value("Retries", str(settings.RetryAttempts), enabled=settings.RetryAttempts>0),
        format_label_value("Chunk Size", f"{settings.ChunkSizeKiB} KiB"),
        format_label_value("Create Root Folder", *bool_label(settings.CreateRootFolder)),
        format_label_value("Show Status Panel", *bool_label(settings.ShowStatusPanel)),
    ]
@dataclass
class RuntimeSettings:
    OutputFolder: Path = Path("downloads")
    OverwriteExisting: bool = False
    ParallelDownloads: int = 4
    RetryAttempts: int = 2
    ChunkSizeKiB: int = 512
    CreateRootFolder: bool = True
    ShowStatusPanel: bool = True
    SettingsPath: Path = field(default_factory=lambda: Path(__file__).parent / "settings.json", repr=False)
    def __post_init__(self):
        self.OutputFolder = self.OutputFolder.expanduser()
    def to_payload(self) -> Dict:
        return {
            "OutputFolder": str(self.OutputFolder),
            "OverwriteExisting": self.OverwriteExisting,
            "ParallelDownloads": self.ParallelDownloads,
            "RetryAttempts": self.RetryAttempts,
            "ChunkSizeKiB": self.ChunkSizeKiB,
            "CreateRootFolder": self.CreateRootFolder,
            "ShowStatusPanel": self.ShowStatusPanel,
        }
    def save(self):
        self.SettingsPath.parent.mkdir(exist_ok=True)
        with self.SettingsPath.open("w", encoding="utf-8") as f:
            json.dump(self.to_payload(), f, indent=2)
    @classmethod
    def load(cls):
        try:
            path = Path(__file__).parent / "settings.json"
            data = json.loads(path.read_text("utf-8"))
            return cls(
                OutputFolder=Path(data.get("OutputFolder", "downloads")),
                OverwriteExisting=bool(data.get("OverwriteExisting", False)),
                ParallelDownloads=int(data.get("ParallelDownloads", 4)),
                RetryAttempts=int(data.get("RetryAttempts", 2)),
                ChunkSizeKiB=int(data.get("ChunkSizeKiB", 512)),
                CreateRootFolder=bool(data.get("CreateRootFolder", True)),
                ShowStatusPanel=bool(data.get("ShowStatusPanel", True)),
            )
        except Exception:
            return cls()
def format_size(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size)
    for unit in units:
        if value < 1024.0:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TiB"
# PROGRESS
class ProgressDisplay:
    def __init__(self):
        self.lock = threading.Lock()
        self.completed = 0
        self.failed = 0
    def update(self, filename: str, percent: str, speed: str):
        with self.lock:
            progress_text = f"Progress: {value_text(percent)} | Speed: {value_text(speed)}"
            print(f"\r{style('[Download]', Palette SYSTEM)} {code_text(filename)} {progress_text}", end="", flush=True)
    def complete(self, filename: str, success: bool):
        with self.lock:
            self.completed += int(success)
            self.failed += int(not success)
            status = success_text("✓ Complete") if success else error_text("✗ Failed")
            print(f"\r{style('[Download]', Palette.SYSTEM)} {code_text(filename)} {status}")
# VIDEO
class VideoTask(threading.Thread):
    def __init__(self, url, format_id, output_dir, progress, retries):
        threading.Thread.__init__(self)
        self.url = url
        self.format_id = format_id
        self.output_dir = output_dir
        self.progress = progress
        self.retries = retries
        self.success = False
        self.error = None
    def run(self):
        attempt = 0
        while attempt <= self.retries:
            try:
                def hook(d):
                    if d['status'] == 'downloading':
                        file = Path(d.get('filename', 'video')).name
                        percent = d.get('_percent_str', 'N/A').strip()
                        speed = d.get('_speed_str', 'N/A').strip()
                        self.progress.update(file, percent, speed)
                    elif d['status'] == 'finished':
                        file = Path(d.get('filename', 'video')).name
                        self.progress.complete(file, True)
                opts = {'format': self.format_id,
                        'outtmpl': str(self.output_dir / '%(title)s.%(ext)s'),
                        'progress_hooks': [hook],
                        'quiet': True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([self.url])
                self.success = True
                return
            except Exception as e:
                attempt += 1
                self.error = str(e)
        self.progress.complete(self.url, False)
# FORMATS
def fetch_formats(url: str):
    try:
        opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = [
                {
                    'format_id': f.get('format_id'),
                    'height': f.get('height', 0),
                    'ext': f.get('ext', ''),
                    'filesize': format_size(f.get('filesize', 0)) if f.get('filesize') else "Unknown size",
                    'fps': f.get('fps', 'N/A'),
                }
                for f in info.get('formats', []) if f.get('vcodec') != 'none' and f.get('acodec') != 'none']
            return info, formats, None
    except Exception as e:
        return None, None, str(e)
def select_format(formats):
    selection = 0
    nav = accent("Use ↑/↓, Enter to select, ESC to cancel.")
    while True:
        clear_console()
        print(style("Select Format", Palette.MAIN + Palette.BOLD))
        for i, fmt in enumerate(formats):
            sel = style('►', Palette.ACCENT) if i == selection else ' '
            text = f"{sel} {fmt['height']}p [{fmt['ext']}] {fmt['filesize']}, {fmt['fps']} fps"
            print(style(text, Palette.HEADER if i == selection else Palette.ACCENT))
        print(nav)
        key = input().lower()
        if key == 'up': selection = (selection - 1) % len(formats)
        elif key == 'down': selection = (selection + 1) % len(formats)
        elif key == 'enter': return formats[selection]
        elif key == 'esc': return None
# DOWNLOAD
def download_videos(tasks, parallel):
    active = []
    for task in tasks:
        while len(active) >= parallel:
            for t in active:
                if not t.is_alive(): active.remove(t)
            time.sleep(0.1)
        task.start()
        active.append(task)
    for t in active:
        t.join()
# MAIN LOGIC
def main():
    settings = RuntimeSettings.load()
    while True:
        clear_console()
        header("Main Menu")
        if settings.ShowStatusPanel:
            print('\n'.join(status_panel(settings)))
            print('')
        print(accent("Choose an option:"))
        opts = ["Download Video", "Settings", "Exit"]
        for i, o in enumerate(opts): print(style(f"{'►' if i==0 else ' '} {o}", Palette.MAIN))
        choice = input().lower()
        if choice == 'download video' or choice == '1':
            clear_console()
            url = input(prompt("Enter video URL")).strip()
            if not url:
                print(warning_text("No URL entered."))
                input(prompt("Press Enter to continue"))
                continue
            info, formats, err = fetch_formats(url)
            if err or not formats:
                print(error_text(f"Failed to fetch formats: {err or 'No formats'}"))
                input(prompt("Press Enter to continue"))
                continue
            selected = select_format(formats)
            if not selected:
                print(warning_text("Download cancelled"))
                continue
            print(value_text(f"Selected: {selected['height']}p [{selected['ext']}] {selected['filesize']}"))
            confirm = input(prompt("Proceed with download? (y/n)")).strip().lower()
            if confirm != 'y': continue
            # Actual download
            progress = ProgressDisplay()
            task = VideoTask(url, selected['format_id'], settings.OutputFolder, progress, settings.RetryAttempts)
            download_videos([task], settings.ParallelDownloads)
            status = success_text("Success") if task.success else error_text(f"Error: {task.error}")
            print(status)
            input(prompt("Press Enter to continue"))
        elif choice == 'settings' or choice == '2':
            clear_console()
            options = [
                ("Output Folder", str(settings.OutputFolder)),
                ("Overwrite Existing", "On" if settings.OverwriteExisting else "Off"),
                ("Parallel Downloads", str(settings.ParallelDownloads)),
                ("Retry Attempts", str(settings.RetryAttempts)),
                ("Chunk Size KiB", str(settings.ChunkSizeKiB)),
                ("Create Root Folder", "On" if settings.CreateRootFolder else "Off"),
                ("Show Status Panel", "On" if settings.ShowStatusPanel else "Off"),
            ]
            print(style("Settings (edit by number):", Palette.HEADER))
            for idx, (name, val) in enumerate(options):
                color = Palette.SUCCESS if val == "On" else Palette.WARNING if val == "Off" else Palette.VALUE
                enabled = val == "On"
                print(f"{idx+1}. {style(name, Palette.MAIN)}: {style(val, color)}")
            print(style("0. Back", Palette.ERROR))
            sel = input(prompt("Select setting to edit"))
            if sel == '0' or sel.lower() == 'back': continue
            try:
                sel = int(sel) - 1
                if sel < 0 or sel >= len(options): continue
            except Exception: continue
            key = options[sel][0]
            if key == "Output Folder":
                new = input(prompt("New output folder"))
                if new: settings.OutputFolder = Path(new).expanduser()
            elif key == "Overwrite Existing":
                settings.OverwriteExisting = not settings.OverwriteExisting
            elif key == "Parallel Downloads":
                val = input(prompt("Parallel downloads count (1-32)"))
                if val.isdigit(): settings.ParallelDownloads = max(1, min(32, int(val)))
            elif key == "Retry Attempts":
                val = input(prompt("Number of retry attempts (0-10)"))
                if val.isdigit(): settings.RetryAttempts = max(0, min(10, int(val)))
            elif key == "Chunk Size KiB":
                val = input(prompt("Chunk Size (64-4096) KiB"))
                if val.isdigit(): settings.ChunkSizeKiB = max(64, min(4096, int(val)))
            elif key == "Create Root Folder":
                settings.CreateRootFolder = not settings.CreateRootFolder
            elif key == "Show Status Panel":
                settings.ShowStatusPanel = not settings.ShowStatusPanel
            settings.save()
            print(success_text("Setting updated."))
            input(prompt("Press Enter to continue"))
        else:
            print(success_text("Goodbye!")); break
if __name__ == "__main__":
    main()
