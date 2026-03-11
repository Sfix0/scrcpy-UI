"""
Localization and Settings Module for scrcpy UI
"""

import os
import sys
import json
import subprocess
import random
import socket
import threading
from datetime import datetime
from zeroconf import ServiceBrowser, Zeroconf, ServiceStateChange

# ==================== BASE PATH (EXE-SAFE) ====================
# When frozen (PyInstaller EXE), use the folder where the EXE lives.
# When running as a script, use the folder where this .py file lives.
if getattr(sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# External tool paths — use exe next to us if present, otherwise fall back to PATH
ADB    = os.path.join(_BASE_DIR, "adb.exe")    if os.path.exists(os.path.join(_BASE_DIR, "adb.exe"))    else "adb"
SCRCPY = os.path.join(_BASE_DIR, "scrcpy.exe") if os.path.exists(os.path.join(_BASE_DIR, "scrcpy.exe")) else "scrcpy"

DATA_DIR = os.path.join(_BASE_DIR, "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LANGUAGE_FILE = os.path.join(DATA_DIR, "language.json")
HELP_FILE = os.path.join(DATA_DIR, "help.md")
os.makedirs(DATA_DIR, exist_ok=True)


# ==================== TRANSLATIONS ====================

DEFAULT_LANG = {
    "app_title": "scrcpy UI", "device": "Device", "connect": "Connect",
    "wifi_ip": "IP:port (Wi-Fi)", "wifi_placeholder": "192.168.1.10:5555",
    "refresh": "Refresh", "status_scanning": "Scanning devices...",
    "status_no_devices": "No devices found", "status_select_device": "Select a device or enter IP!",
    "status_connection_failed": "Failed to connect to", "status_device_not_found": "Connected device not found",
    "status_launching": "Launching scrcpy for", "status_recording": "with recording",
    "settings": "Settings", "settings_title": "Settings", "settings_debug": "Debug Overlay",
    "settings_extended": "Extended metrics", "settings_extended_desc": "(CPU frequencies and graphics FPS)",
    "settings_behavior": "Application Behavior", "settings_hide_console": "Hide scrcpy console",
    "settings_kill_adb": "Try to kill ADB on exit",
    "resolution": "Resolution", "native": "Native (no limit)", "resolution_100": "100% (Full)",
    "custom": "Custom %...", "fps_unlimited": "FPS unlimited in Native mode",
    "bitrate": "Bitrate", "bitrate_low": "Low (2 Mbps)", "bitrate_standard": "Standard (8 Mbps)",
    "bitrate_high": "High (15 Mbps)", "bitrate_max": "Maximum (30 Mbps)",
    "keyboard_input": "Keyboard Input",
    "keyboard_sdk": "SDK (English only)", "keyboard_uhid": "UHID (multilingual)",
    "keyboard_text": "SDK + Text",
    "recording": "Screen Recording",
    "enable_recording": "Record screen", "record_path": "Recording path",
    "shortcuts": "Shortcuts", "file_manager": "File Manager",
    "help": "How to Connect?", "create_shortcut": "Create Shortcut", "close": "Close",
    "debug_control_panel": "Debug & Control Panel",
    "clipboard": "Clipboard Sync",
    "clipboard_enable": "Enable clipboard synchronization",
    "clipboard_desc": "(Copy on PC → Paste on Phone and vice versa)",
    "toggle_orientation": "Toggle phone orientation",
    "keyboard_and_clipboard": "Keyboard & Clipboard",
    "resolution_percent": "Quality",
    "custom_percent_hint": "Enter percentage (10-100)",
    
    # File Manager translations
    "fm_title": "File Manager - {device_name}",
    "fm_col_name": "Name",
    "fm_col_size": "Size",
    "fm_col_date": "Date",
    "fm_col_type": "Type",
    "fm_unknown": "Unknown",
    "fm_folder_type": "[Folder]",
    "fm_type_image": "Image",
    "fm_type_video": "Video",
    "fm_type_audio": "Audio",
    "fm_type_archive": "Archive",
    "fm_type_document": "Document",
    "fm_type_unknown": "File",
    "fm_path": "Path",
    "fm_info": "Info",
    "fm_info_title": "File Information",
    "fm_download": "Download",
    "fm_upload": "Upload",
    "fm_rename": "Rename",
    "fm_delete": "Delete",
    "fm_new_folder": "New Folder",
    "fm_copy": "Copy",
    "fm_cut": "Cut",
    "fm_select_folder": "Select folder to save files...",
    "fm_delete_confirm": "Delete {count} file(s)?",
    "fm_status_single": "{count} items",
    "fm_status_multiple": "{count} selected of {count} items",
    "fm_opening": "Opening {filename}...",
    "fm_downloading": "Downloading {filename}...",
    "fm_downloading_progress": "Downloading {filename} ({current}/{total})...",
    "fm_downloaded_to": "Downloaded {count} file(s) to {path}",
    "fm_uploading_progress": "Uploading {filename} ({current}/{total})...",
    "fm_uploaded": "Uploaded {count} file(s)",
    "fm_deleting_progress": "Deleting... ({current}/{total})",
    "fm_deleted": "Deleted {count} item(s)",
    "fm_pasted": "Pasted {count} item(s)",
    "fm_created": "Created: {folder_name}",
    "fm_renamed": "Renamed to: {filename}",
    "fm_opened": "Opened: {filename}",
    "fm_failed_open": "Failed to open: {filename}",
    "fm_error": "Error: {message}",
    "fm_back": "Back",
    "fm_home": "Home",
    "fm_select_mode": "Selection Mode",
    "fm_select_all": "Select All",
    "fm_cancel_selection": "Cancel Selection",
    "fm_empty_folder": "Folder is empty",
    "fm_paste_count": "Paste ({count})",
    "fm_folder_name_hint": "Folder name",

    # Keyboard Shortcuts translations
    "shortcuts_title": "Keyboard Shortcuts",
    "shortcuts_screen": "Screen Control",
    "shortcuts_window": "Window Size",
    "shortcuts_navigation": "Navigation",
    "shortcuts_warning": "Use LEFT Alt!",
    "shortcut_fullscreen": "Fullscreen",
    "shortcut_screen_off": "Screen on/off",
    "shortcut_power": "Power button",
    "shortcut_resize": "Resize (1:1)",
    "shortcut_fit": "Remove bars",
    "shortcut_volume_up": "Volume +",
    "shortcut_volume_down": "Volume -",
    "shortcut_home": "HOME",
    "shortcut_back": "BACK",

    # Toggle button tooltips
    "tooltip_hevc": "H.265 (HEVC) — more efficient codec, less traffic.\nRequires device support.",
    "tooltip_fullscreen": "Launch in fullscreen mode",
    "tooltip_stay_awake": "Keep device screen on while mirroring",
    "tooltip_turn_screen_off": "Turn off device screen while mirroring",

    # About dialog
    "about_title": "About",
    "about_gui_section": "INTERFACE",
    "about_gui_desc": "GUI for scrcpy",
    "about_author": "Author",
    "about_based_on": "BASED ON",
    "about_version": "Version",
    "about_license": "License",
    "about_donate": "Donate",
    "about_font_section": "FONT",
    "about_framework_section": "UI FRAMEWORK",
}


# ==================== UI CONSTANTS ====================

# Default window dimensions
DEFAULT_WINDOW_WIDTH = 483
DEFAULT_WINDOW_HEIGHT = 650
MIN_WINDOW_WIDTH = 450
MIN_WINDOW_HEIGHT = 600

# Resolution percentage options
RESOLUTION_OPTIONS = [
    "native",           # Native (no limit) - unlimited FPS
    "100%",             # 100% (Full) - full resolution, controllable FPS
    "80%",              # High quality
    "60%",              # Medium quality
    "custom",           # Custom percentage
]

# Bitrate options for video streaming
BITRATE_OPTIONS = {
    "2M": "Low (2 Mbps)",
    "8M": "Standard (8 Mbps)",
    "15M": "High (15 Mbps)",
    "30M": "Maximum (30 Mbps)",
}

# Keyboard input modes
KEYBOARD_MODES = {
    "sdk": "SDK (English only)",
    "uhid": "UHID (multilingual)",
    "text": "SDK + Text",
}

# FPS slider configuration
FPS_MIN = 10
FPS_MAX = 120
FPS_DEFAULT = 60
FPS_DIVISIONS = 110

# ========== FONT UTILITIES ==========
def find_custom_font():
    """Find first .ttf/.otf font file in data/ directory (alphabetical order)"""
    font_dir = DATA_DIR
    if not os.path.exists(font_dir):
        return None
    
    # Collect all font files (.ttf and .otf, case-insensitive)
    font_files = [
        f for f in os.listdir(font_dir) 
        if f.lower().endswith(('.ttf', '.otf'))
    ]
    
    if not font_files:
        return None
    
    # Sort alphabetically and return first
    font_files.sort()
    return os.path.join(font_dir, font_files[0])


# ==================== SETTINGS MANAGER ====================

class SettingsManager:
    """Settings manager with JSON persistence"""

    def __init__(self):
        self.settings_file = SETTINGS_FILE
        self.default_settings = {
            "theme": "dark", "language": "en", "window_width": DEFAULT_WINDOW_WIDTH,
            "window_height": DEFAULT_WINDOW_HEIGHT, "window_left": None, "window_top": None,
            "resolution": "100%", "max_fps": FPS_DEFAULT, "bit_rate": "8M",
            "use_hevc": False, "keyboard_mode": "uhid", "fullscreen": False,
            "stay_awake": True, "turn_screen_off": False, "record_enabled": False,
            "hide_console": True, "kill_adb_on_exit": False, "extended_metrics": False,
            "clipboard_sync": False, "debug_panel_scale": 1.0
        }
        self.settings = self.load()

    def load(self):
        """Load settings from JSON file in data/ directory or return defaults"""
        old_path = "settings.json"
        new_path = os.path.join(DATA_DIR, "settings.json")
        
        # Migrate from root if exists and new doesn't
        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                os.rename(old_path, new_path)
            except:
                pass
        
        if os.path.exists(new_path):
            try:
                with open(new_path, 'r', encoding='utf-8') as f:
                    return {**self.default_settings, **json.load(f)}
            except Exception:
                return self.default_settings.copy()
        return self.default_settings.copy()

    def save(self):
        """Save current settings to JSON file in data/ directory"""
        settings_path = os.path.join(DATA_DIR, "settings.json")
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get(self, key, default=None):
        """Get setting value by key"""
        return self.settings.get(key, default)

    def set(self, key, value):
        """Set setting value and save"""
        self.settings[key] = value
        self.save()

    def save_window_size(self, width, height, left=None, top=None):
        """Save window dimensions"""
        self.settings["window_width"] = width
        self.settings["window_height"] = height
        if left is not None:
            self.settings["window_left"] = left
        if top is not None:
            self.settings["window_top"] = top
        self.save()


# ==================== LANGUAGE MANAGER ====================

class LanguageManager:
    """Language and translation manager"""

    def __init__(self, settings_manager=None):
        self.settings_manager = settings_manager
        self.translations = {"en": DEFAULT_LANG.copy()}
        self.current_lang = "en"

        # Load custom translations from language.json
        self._load_custom_translations()

        # Set initial language from settings or defaults
        initial_lang = "en"
        if self.settings_manager:
            initial_lang = self.settings_manager.get("language", "en")
        self.set_language(initial_lang)

    def _load_custom_translations(self):
        """Load additional translations from language.json in data/ directory"""
        # Check both locations for backward compatibility
        paths_to_check = [
            os.path.join(DATA_DIR, "language.json"),
            "language.json"  # Fallback to root (for migration)
        ]
        
        for lang_path in paths_to_check:
            if os.path.exists(lang_path):
                try:
                    with open(lang_path, 'r', encoding='utf-8') as f:
                        custom = json.load(f)
                        for lang_code, translations in custom.items():
                            if lang_code.startswith('_'):
                                continue
                            
                            if lang_code in self.translations:
                                base = self.translations[lang_code].copy()
                            elif lang_code == "en":
                                base = DEFAULT_LANG.copy()
                            else:
                                base = DEFAULT_LANG.copy()
                            
                            base.update(translations)
                            self.translations[lang_code] = base
                        
                        # Migrate from root to data/ if needed
                        if lang_path == "language.json" and not os.path.exists(os.path.join(DATA_DIR, "language.json")):
                            try:
                                os.rename("language.json", os.path.join(DATA_DIR, "language.json"))
                            except:
                                pass
                        break
                except Exception:
                    pass

    def set_language(self, lang):
        """Set current language and persist if settings manager available"""
        self.current_lang = lang if lang in self.translations else "en"
        if self.settings_manager:
            self.settings_manager.set("language", self.current_lang)

    def t(self, key):
        """Get translated string by key, fallback to DEFAULT_LANG or key itself"""
        # Check if key exists in current language translations
        if self.current_lang in self.translations:
            if key in self.translations[self.current_lang]:
                return self.translations[self.current_lang][key]
        
        # Fallback to DEFAULT_LANG
        if key in DEFAULT_LANG:
            return DEFAULT_LANG[key]
        
        # Return key itself if not found
        return key

    def get_language_name(self):
        """Get display name for current language"""
        if self.current_lang in self.translations:
            lang_data = self.translations[self.current_lang]
            if "_name" in lang_data:
                return lang_data["_name"]
            return self.current_lang.upper()
        return "EN"

    def get_next_language_name(self):
        """Get display name for next language (for toggle button)"""
        available = self.available_languages()
        if not available:
            return "EN"
        current_idx = available.index(self.current_lang) if self.current_lang in available else 0
        next_idx = (current_idx + 1) % len(available)
        next_lang = available[next_idx]

        if next_lang in self.translations:
            lang_data = self.translations[next_lang]
            if "_name" in lang_data:
                return lang_data["_name"]
            return next_lang.upper()
        return "EN"

    def available_languages(self):
        """Get list of available language codes (excluding internal keys)"""
        return [k for k in self.translations.keys() if not k.startswith('_')]


# ==================== HELPER FUNCTIONS ====================

def check_scrcpy_clipboard_support():
    """Check if current scrcpy version supports clipboard parameter"""
    try:
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            [SCRCPY, "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        return "--clipboard-sync" in result.stdout
    except Exception:
        return False


def calculate_max_size(resolution_str, percent):
    """
    Calculate max-size value based on device resolution and percentage.

    Args:
        resolution_str: Resolution string like "1220x2712"
        percent: Percentage (1-100)

    Returns:
        max-size value as string, or None if calculation fails
    """
    try:
        if not resolution_str or "x" not in resolution_str:
            return None

        width, height = resolution_str.split("x")
        max_side = max(int(width), int(height))
        result = int(max_side * percent / 100)

        if result < 100:
            return None  # Too small, would be useless
        return str(result)
    except (ValueError, AttributeError):
        return None


# ==================== ADB HELPER FUNCTIONS ====================

def run_adb_command(args):
    """Execute ADB command and return output with hidden console"""
    try:
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
        
        result = subprocess.run(
            [ADB] + args, 
            capture_output=True, 
            text=True, 
            timeout=5,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        return result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return "", str(e)


def get_connected_devices():
    """Get list of connected ADB devices"""
    out, _ = run_adb_command(["devices"])
    devices = []
    for line in out.splitlines()[1:]:
        if "\t" in line:
            serial, status = line.split("\t", 1)
            if status == "device":
                devices.append(serial)
    return devices


def get_device_battery(serial):
    """Get battery level for device"""
    out, _ = run_adb_command(["-s", serial, "shell", "dumpsys", "battery"])
    for line in out.splitlines():
        if "level:" in line:
            try:
                return int(line.split(":")[1].strip())
            except Exception:
                return None
    return None


def get_battery_icon_and_color(level, is_charging=False):
    """Get battery icon and color based on level and charging state"""
    try:
        import flet as ft
    except ImportError:
        return "BATTERY_UNKNOWN", "#808080"

    if is_charging:
        return ft.icons.BATTERY_CHARGING_FULL, ft.colors.GREEN
    if level is None:
        return ft.icons.BATTERY_UNKNOWN, ft.colors.GREY
    if level >= 80:
        return ft.icons.BATTERY_FULL, ft.colors.GREEN
    elif level >= 60:
        return ft.icons.BATTERY_5_BAR, ft.colors.LIGHT_GREEN
    elif level >= 40:
        return ft.icons.BATTERY_4_BAR, ft.colors.ORANGE
    elif level >= 20:
        return ft.icons.BATTERY_3_BAR, ft.colors.ORANGE
    else:
        return ft.icons.BATTERY_ALERT, ft.colors.RED


def is_device_charging(serial):
    """Check if device is charging"""
    out, _ = run_adb_command(["-s", serial, "shell", "dumpsys", "battery"])
    for line in out.splitlines():
        if "AC powered:" in line or "USB powered:" in line or "Wireless powered:" in line:
            if "true" in line:
                return True
    return False


def get_device_info(serial):
    """Get comprehensive device information"""
    model = "Unknown Model"
    android = "?"
    resolution = "unknown"
    battery = get_device_battery(serial)

    out, _ = run_adb_command(["-s", serial, "shell", "getprop", "ro.product.marketname"])
    if out.strip():
        model = out.strip()
    else:
        out, _ = run_adb_command(["-s", serial, "shell", "getprop", "ro.product.model"])
        if out.strip():
            model = out.strip()

    out, _ = run_adb_command(["-s", serial, "shell", "getprop", "ro.build.version.release"])
    if out.strip():
        android = out.strip()

    out, _ = run_adb_command(["-s", serial, "shell", "wm", "size"])
    if "Physical size:" in out:
        resolution = out.split(":")[1].strip()

    return {
        "model": model,
        "android": android,
        "resolution": resolution,
        "serial": serial,
        "battery": battery
    }


def connect_wifi_device(ip):
    """Connect to device via WiFi using ADB connect"""
    out, _ = run_adb_command(["connect", ip])

    if "connected" in out.lower() or "already connected" in out.lower():
        return True
    if "connection refused" in out.lower():
        return False
    if "cannot connect" in out.lower():
        return False

    return "connected" in out or "already connected" in out



def get_default_record_path():
    """Get default path for screen recordings"""
    videos_dir = os.path.join(os.path.expanduser("~"), "Videos", "scrcpy_ui")
    os.makedirs(videos_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(videos_dir, f"scrcpy_{timestamp}.mp4")


def create_shortcut(serial, args, model_name):
    """Create Windows shortcut on desktop"""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    safe_name = "".join(c for c in model_name if c.isalnum() or c in " _-").strip()
    if not safe_name or safe_name == "Unknown Model":
        safe_name = "Device"
    safe_name = safe_name.replace(" ", "_")
    bat_path = os.path.join(desktop, f"{safe_name}.bat")

    cmd_line = f'scrcpy --serial={serial} ' + ' '.join(f'"{arg}"' if ' ' in str(arg) else str(arg) for arg in args)
    content = f'@echo off\ncd /d "{_BASE_DIR}"\n{cmd_line}\npause\n'
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(content)
    return bat_path


def kill_adb_server():
    """Kill ADB server - comprehensive Windows cleanup with hidden console"""
    try:
        # Check both possible locations for settings file
        settings_file = None
        for path in [os.path.join(DATA_DIR, "settings.json"), "settings.json"]:
            if os.path.exists(path):
                settings_file = path
                break

        # If no settings file found OR kill_adb_on_exit is False → do not kill
        if settings_file is None:
            return
        
        with open(settings_file, 'r', encoding='utf-8') as f:
            settings_data = json.load(f)
        
        if not settings_data.get("kill_adb_on_exit", False):
            return

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
        
        # Kill adb.exe processes
        subprocess.run(
            ['taskkill', '/F', '/IM', 'adb.exe'],
            capture_output=True,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        time.sleep(0.1)
        
        # Kill AdbWinApi.dll processes (if any)
        subprocess.run(
            ['taskkill', '/F', '/IM', 'AdbWinApi.dll'],
            capture_output=True,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        time.sleep(0.1)
        
        # Kill AdbWinExt.dll processes (if any)
        subprocess.run(
            ['taskkill', '/F', '/IM', 'AdbWinExt.dll'],
            capture_output=True,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        time.sleep(0.1)
        
        # Final adb kill-server command
        subprocess.run(
            [ADB, "kill-server"],
            capture_output=True,
            timeout=5,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
    except Exception:
        pass


# ==================== HELPER FUNCTIONS FOR UI ====================

def load_help_content(lang_code):
    """Load help content from help.md in data/ directory"""
    # Check both locations for backward compatibility
    paths_to_check = [
        os.path.join(DATA_DIR, "help.md"),
        "help.md"  # Fallback to root
    ]
    
    for help_path in paths_to_check:
        if os.path.exists(help_path):
            try:
                import re
                with open(help_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                pattern = r'===\s*(\w+)\s*===\s*\n(.*?)(?=\n===\s\w+\s*===|$)'
                matches = re.findall(pattern, content, re.DOTALL)
                help_sections = {lang: text.strip() for lang, text in matches}
                if lang_code in help_sections:
                    return help_sections[lang_code]
                if 'en' in help_sections:
                    return help_sections['en']
            except Exception:
                pass
            break
    
    # Default help content
    return """# How to Connect Your Android Device
USB Connection
Enable Developer Options (tap Build number 7 times)
Enable USB Debugging
Connect USB cable and accept prompt
Wi-Fi Connection (Android 11+)
Connect via USB first
Enable Wireless debugging
Note IP:port
Enter in app and connect
Visit: https://github.com/Genymobile/scrcpy
"""


# ==================== FACTORY FUNCTION ====================

def create_managers():
    """
    Factory function to create SettingsManager and LanguageManager together.
    Returns tuple of (SettingsManager, LanguageManager)
    """
    settings = SettingsManager()
    lang_manager = LanguageManager(settings)
    return settings, lang_manager
   
# ==================== NETWORK UTILS ====================

def get_local_network_prefix():  # Determines the local IP of the PC and returns the network prefix (e.g. '192.168.1.')
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        # Cut off the last number (192.168.31.10 -> 192.168.31.)
        prefix = local_ip.rsplit('.', 1)[0] + "."
        return prefix
    except Exception:
        return ""

# ==================== WIFI DISCOVERY (mDNS / Zeroconf) ====================

class WifiDiscovery:
    """
    Listens for Android devices advertising themselves via mDNS.
    Android 11+ with Wireless Debugging enabled broadcasts:
      _adb-tls-connect._tcp.local.  — for connecting (after pairing)
      _adb-tls-pairing._tcp.local.  — for first-time pairing (PIN/QR)
    """

    SERVICE_CONNECT = "_adb-tls-connect._tcp.local."
    SERVICE_PAIRING = "_adb-tls-pairing._tcp.local."

    def __init__(self, on_device_found=None, on_device_lost=None):
        self.on_device_found = on_device_found
        self.on_device_lost = on_device_lost
        self._zeroconf = None
        self._browser = None
        self._found_devices = {}
        self._lock = threading.Lock()

    def _on_service_state_change(self, zeroconf, service_type, name, state_change):
        if state_change is ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info is None:
                return
            addresses = info.parsed_addresses()
            if not addresses:
                return
            ip = addresses[0]
            port = info.port
            display_name = name.replace(f".{service_type}", "").strip()
            with self._lock:
                self._found_devices[name] = (ip, port)
            if self.on_device_found:
                self.on_device_found(display_name, ip, port)

        elif state_change is ServiceStateChange.Removed:
            display_name = name.replace(f".{service_type}", "").strip()
            with self._lock:
                self._found_devices.pop(name, None)
            if self.on_device_lost:
                self.on_device_lost(display_name)

    def start(self):
        if self._zeroconf is not None:
            return
        self._zeroconf = Zeroconf()
        self._browser = ServiceBrowser(
            self._zeroconf,
            [self.SERVICE_CONNECT, self.SERVICE_PAIRING],
            handlers=[self._on_service_state_change]
        )

    def stop(self):
        if self._zeroconf:
            self._zeroconf.close()
            self._zeroconf = None
            self._browser = None

    def get_found_devices(self):
        with self._lock:
            return dict(self._found_devices)