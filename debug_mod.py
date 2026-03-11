"""
Debug & Control Panel for Scrcpy UI ( Flet )
Version: Socket IPC Implementation (Fixed Subprocess Launch)
"""

import flet as ft
import subprocess
import threading
import time
import os
import re
import sys
import psutil
import tempfile
import json
import socket
from datetime import datetime
from collections import deque

# Import ADB path from localization (works both in script and EXE mode)
try:
    from localization import ADB, DATA_DIR as _DATA_DIR
except ImportError:
    ADB = "adb"
    _DATA_DIR = "data"

# ==================== SETTINGS LOADER ====================

def load_scale_from_settings():
    """Load debug_panel_scale from settings.json"""
    settings_path = os.path.join(_DATA_DIR, "settings.json")
    try:
        if os.path.exists(settings_path):
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                scale = settings.get("debug_panel_scale", 1.0)
                if isinstance(scale, (int, float)) and 0.5 <= scale <= 2.0:
                    return float(scale)
    except Exception:
        pass
    return 1.0

# ==================== CONTROL PANEL ====================

class AdvancedControlPanel:

    def __init__(self, serial, scrcpy_process=None, mode="standard", is_overlay=False, ipc_port=None):
        self.serial = serial
        self.scrcpy_process = scrcpy_process
        self.mode = mode
        self.is_overlay = is_overlay
        self.running = False
        self.closing = False

        # IPC (Inter-Process Communication)
        self.ipc_port = ipc_port
        self.server_socket = None
        self.client_conn = None

        self.last_cpu_stats = None
        self.labels = {}
        self.update_counter = 0
        self.current_fps = "0.0"
        self.fps_history = deque(maxlen=30)
        self.fps_bars = []
        self.page = None
        
        self.cached_gpu_model = "Detecting..."
        self.current_soc_temp = None

        self.scale = load_scale_from_settings()

        # Start the socket server if this is the main process (holding the scrcpy handle)
        if self.scrcpy_process and not self.is_overlay:
            self._start_socket_server()

    # ---------- IPC HELPER METHODS (SOCKETS) ----------

    def _start_socket_server(self):
        """Starts a TCP server to stream FPS data to the child process"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind(('127.0.0.1', 0)) # Bind to any free port
            self.ipc_port = self.server_socket.getsockname()[1]
            self.server_socket.listen(1)
            
            def accept_client():
                try:
                    conn, _ = self.server_socket.accept()
                    self.client_conn = conn
                except:
                    pass
            
            threading.Thread(target=accept_client, daemon=True).start()
        except Exception as e:
            print(f"Socket server error: {e}")

    # ---------- SCALE HELPER METHODS ----------
    
    def s(self, value):
        return int(value * self.scale) if isinstance(value, (int, float)) else value
    
    def sf(self, value):
        return value * self.scale if isinstance(value, (int, float)) else value

    # ---------- PUBLIC ----------

    def create_window(self):
        # Start the thread that reads Scrcpy output and sends it to the socket
        if self.scrcpy_process:
            threading.Thread(target=self._relay_scrcpy_fps_socket, daemon=True).start()

        # Launch the separate Flet process
        threading.Thread(
            target=self._run_subprocess,
            args=(self.serial, self.mode, self.ipc_port),
            daemon=True
        ).start()

    def _relay_scrcpy_fps_socket(self):
        """Reads stdout from scrcpy and sends it via socket to the UI process"""
        if not self.scrcpy_process or not hasattr(self.scrcpy_process, 'stdout'): 
            return
        
        fps_re = re.compile(r'(\d+\.?\d*)\s*fps', re.IGNORECASE)
        
        try:
            while self.scrcpy_process.poll() is None and not self.closing:
                # Read line from Scrcpy
                line = self.scrcpy_process.stdout.readline()
                if not line:
                    if self.scrcpy_process.poll() is not None: break
                    time.sleep(0.005)
                    continue

                # Parse FPS locally
                match = fps_re.search(line)
                if match and self.client_conn:
                    try:
                        # Send just the number and a newline
                        fps_val = match.group(1) + "\n"
                        self.client_conn.sendall(fps_val.encode('utf-8'))
                    except (BrokenPipeError, ConnectionResetError):
                        self.client_conn = None # Client disconnected
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            if self.client_conn:
                try: self.client_conn.close()
                except: pass
            if self.server_socket:
                try: self.server_socket.close()
                except: pass

    def _run_subprocess(self, serial, mode, port):
        try:
            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW
            
            if getattr(sys, 'frozen', False):
                args = [sys.executable, "--flet-panel", serial, mode]
            else:
                current_script = os.path.abspath(__file__)
                args = [sys.executable, current_script, "--flet-panel", serial, mode]
            
            if port:
                args.append(str(port))

            subprocess.Popen(
                args,
                startupinfo=startupinfo,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=os.getcwd()
            )
        except Exception as e:
            print(f"Failed to launch debug panel: {e}")

    # ---------- UI ----------

    def _main(self, page: ft.Page):
        self.page = page
        self.running = True

        def on_window_event(e):
            if e.data == "close":
                self.close()
        
        page.window.on_event = on_window_event
        page.window.prevent_close = True
        page.title = "Debug Panel"
        
        page.window.width = self.s(360)
        heights = {"standard": 550, "extended": 850}
        page.window.height = self.s(heights.get(self.mode, 550))
        
        page.window.always_on_top = True
        page.window.resizable = False
        page.window.frameless = True
        page.window.title_bar_hidden = True
        page.window.opacity = 0.78
        page.bgcolor = ft.colors.TRANSPARENT
        page.window.bgcolor = ft.colors.TRANSPARENT
        page.padding = 0
        page.theme_mode = ft.ThemeMode.DARK
        page.window.left = 5
        page.window.top = 5

        # Apply custom font if available (matches main UI)
        try:
            from localization import find_custom_font
            custom_font = find_custom_font()
            if custom_font:
                page.fonts = {"CustomFont": custom_font}
                page.theme = ft.Theme(font_family="CustomFont")
        except Exception:
            pass

        # UI Components
        self.labels["fps"] = ft.Text("FPS: 0.0", size=self.sf(11), weight=ft.FontWeight.BOLD, color=ft.colors.CYAN_400)
        self.labels["cpu"] = ft.Text("N/A", size=self.sf(11), color=ft.colors.CYAN_300)
        self.labels["battery"] = ft.Text("N/A", size=self.sf(11), color=ft.colors.YELLOW_400)
        self.labels["ram"] = ft.Text("N/A", size=self.sf(11), color=ft.colors.ORANGE_400)
        self.labels["gpu"] = ft.Text("N/A", size=self.sf(11), color=ft.colors.PURPLE_400)
        self.labels["brightness"] = ft.Text("N/A", size=self.sf(11), color=ft.colors.AMBER_400)
        self.labels["charging"] = ft.Icon(ft.icons.ELECTRIC_BOLT, size=self.s(12), color=ft.colors.GREEN_400, visible=False)

        def grid_metric(icon, icon_color, value_label, extra=None):
            row = ft.Row([ft.Icon(icon, size=self.s(16), color=icon_color), value_label], spacing=self.s(6))
            if extra: row.controls.append(extra)
            return ft.Container(
                content=row, 
                padding=self.s(8), 
                border_radius=self.s(8), 
                bgcolor=ft.colors.with_opacity(0.05, ft.colors.WHITE), 
                expand=True
            )

        metrics_grid = ft.Column([
            ft.Row([grid_metric(ft.icons.MEMORY, ft.colors.CYAN_300, self.labels["cpu"]), grid_metric(ft.icons.SPEED, ft.colors.CYAN_400, self.labels["fps"])], spacing=self.s(6)),
            ft.Row([grid_metric(ft.icons.BATTERY_CHARGING_FULL, ft.colors.YELLOW_400, self.labels["battery"], self.labels["charging"]), grid_metric(ft.icons.STORAGE_ROUNDED, ft.colors.ORANGE_400, self.labels["ram"])], spacing=self.s(6)),
            ft.Row([grid_metric(ft.icons.GRID_VIEW_ROUNDED, ft.colors.PURPLE_400, self.labels["gpu"]), grid_metric(ft.icons.BRIGHTNESS_6, ft.colors.AMBER_400, self.labels["brightness"])], spacing=self.s(6)),
        ], spacing=self.s(6), tight=True)

        metrics_section = ft.Container(
            padding=ft.padding.symmetric(horizontal=self.s(10), vertical=self.s(8)), 
            border_radius=self.s(8),
            bgcolor=ft.colors.with_opacity(0.15, ft.colors.BLACK),
            content=ft.Column([
                ft.Row([ft.Icon(ft.icons.ANALYTICS, size=self.s(16), color=ft.colors.CYAN_400), ft.Text("METRICS", size=self.sf(11), weight=ft.FontWeight.BOLD, color=ft.colors.CYAN_400)], spacing=self.s(6)),
                ft.Divider(height=self.s(4), thickness=1, color=ft.colors.with_opacity(0.2, ft.colors.CYAN_400)), 
                metrics_grid
            ], spacing=self.s(8), tight=True)
        )

        def icon_btn(icon, callback, tip, color=ft.colors.CYAN_300):
            return ft.Container(
                content=ft.IconButton(icon=icon, icon_size=self.s(22), icon_color=color, tooltip=tip, on_click=lambda _: callback()), 
                border_radius=self.s(8), 
                bgcolor=ft.colors.with_opacity(0.08, ft.colors.WHITE)
            )

        # Animated screenshot button
        screenshot_btn_container = ft.Container(
            content=ft.IconButton(
                icon=ft.icons.CAMERA_ALT, icon_size=self.s(22),
                icon_color=ft.colors.PURPLE_300, tooltip="Screenshot",
                on_click=lambda _: self._screenshot_with_flash(screenshot_btn_container)
            ),
            border_radius=self.s(8),
            bgcolor=ft.colors.with_opacity(0.08, ft.colors.WHITE),
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )

        quick_actions = ft.Container(
            padding=ft.padding.symmetric(horizontal=self.s(14), vertical=self.s(12)), 
            border_radius=self.s(8),
            bgcolor=ft.colors.with_opacity(0.15, ft.colors.BLACK),
            content=ft.Column([
                ft.Row([ft.Icon(ft.icons.TOUCH_APP, size=self.s(16), color=ft.colors.CYAN_400), ft.Text("QUICK ACTIONS", size=self.sf(11), weight=ft.FontWeight.BOLD, color=ft.colors.CYAN_400)], spacing=self.s(6)),
                ft.Divider(height=self.s(4), thickness=1, color=ft.colors.with_opacity(0.2, ft.colors.CYAN_400)),
                ft.Row([icon_btn(ft.icons.HOME, self.press_home, "Home"), icon_btn(ft.icons.ARROW_BACK, self.press_back, "Back"), icon_btn(ft.icons.APPS, self.press_recent, "Apps"), icon_btn(ft.icons.LOCK, self.press_power, "Lock", ft.colors.RED_300)], spacing=self.s(8), alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                ft.Row([screenshot_btn_container, icon_btn(ft.icons.VOLUME_UP, self.volume_up, "Vol+"), icon_btn(ft.icons.VOLUME_DOWN, self.volume_down, "Vol-")], spacing=self.s(8), alignment=ft.MainAxisAlignment.SPACE_EVENLY),
            ], spacing=self.s(8), tight=True)
        ) if self.mode in ["standard", "extended"] else None

        screen_control = ft.Container(
            padding=ft.padding.symmetric(horizontal=self.s(14), vertical=self.s(12)), 
            border_radius=self.s(8),
            bgcolor=ft.colors.with_opacity(0.15, ft.colors.BLACK),
            content=ft.Column([
                ft.Row([ft.Icon(ft.icons.SCREEN_ROTATION, size=self.s(16), color=ft.colors.CYAN_400), ft.Text("SCREEN", size=self.sf(11), weight=ft.FontWeight.BOLD, color=ft.colors.CYAN_400)], spacing=self.s(6)),
                ft.Divider(height=self.s(4), thickness=1, color=ft.colors.with_opacity(0.2, ft.colors.CYAN_400)),
                ft.Row([icon_btn(ft.icons.ZOOM_IN, self.toggle_zoom, "Zoom"), icon_btn(ft.icons.SCREEN_ROTATION, self.toggle_rotation, "Rotate"), icon_btn(ft.icons.SCREEN_LOCK_ROTATION, self.toggle_autorotation, "Auto Rotation")], spacing=self.s(8), alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                ft.Row([
                    icon_btn(ft.icons.KEYBOARD_ARROW_LEFT, lambda: self.swipe_right(), "Swipe Left"),
                    icon_btn(ft.icons.KEYBOARD_ARROW_UP, lambda: self.swipe_up(), "Swipe Up"),
                    icon_btn(ft.icons.KEYBOARD_ARROW_DOWN, lambda: self.swipe_down(), "Swipe Down"),
                    icon_btn(ft.icons.KEYBOARD_ARROW_RIGHT, lambda: self.swipe_left(), "Swipe Right"),
                ], spacing=self.s(8), alignment=ft.MainAxisAlignment.SPACE_EVENLY),
            ], spacing=self.s(8), tight=True)
        ) if self.mode in ["standard", "extended"] else None

        system_control = ft.Container(
            padding=ft.padding.symmetric(horizontal=self.s(14), vertical=self.s(12)), 
            border_radius=self.s(8),
            bgcolor=ft.colors.with_opacity(0.15, ft.colors.BLACK),
            content=ft.Column([
                ft.Row([ft.Icon(ft.icons.SETTINGS_SYSTEM_DAYDREAM, size=self.s(16), color=ft.colors.CYAN_400), ft.Text("SYSTEM", size=self.sf(11), weight=ft.FontWeight.BOLD, color=ft.colors.CYAN_400)], spacing=self.s(6)),
                ft.Divider(height=self.s(4), thickness=1, color=ft.colors.with_opacity(0.2, ft.colors.CYAN_400)),
                ft.Row([icon_btn(ft.icons.PLAY_ARROW, self.media_play_pause, "Play/Pause"), icon_btn(ft.icons.SKIP_NEXT, self.media_next, "Next"), icon_btn(ft.icons.SKIP_PREVIOUS, self.media_previous, "Previous"), icon_btn(ft.icons.VOLUME_MUTE, self.mute_volume, "Mute", ft.colors.ORANGE_300)], spacing=self.s(8), alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                ft.Row([icon_btn(ft.icons.DO_NOT_DISTURB_ON, self.toggle_dnd, "Do Not Disturb", ft.colors.AMBER_400), icon_btn(ft.icons.CLEAR_ALL, self.clear_recent_apps, "Clear Recent Apps", ft.colors.RED_300)], spacing=self.s(8), alignment=ft.MainAxisAlignment.SPACE_EVENLY),
            ], spacing=self.s(8), tight=True)
        ) if self.mode == "extended" else None

        extended_metrics = None
        if self.mode == "extended":
            self._create_fps_bars()
            fps_graph_widget = ft.Container(
                content=ft.Column([
                    ft.Text("FPS Graph", size=self.sf(10), color=ft.colors.CYAN_400, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=ft.Row(self.fps_bars, spacing=1, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, expand=True),
                        height=self.s(45), padding=self.s(5), border_radius=self.s(6),
                        bgcolor=ft.colors.with_opacity(0.1, ft.colors.BLACK),
                        border=ft.border.all(1, ft.colors.with_opacity(0.3, ft.colors.CYAN_600)),
                        expand=True
                    )
                ], spacing=self.s(4), tight=True),
                padding=ft.padding.symmetric(vertical=self.s(6)), expand=True
            )
            self.labels["cpu_cores"] = [ft.Text(f"C{i}: N/A", size=self.sf(9), color=ft.colors.CYAN_300) for i in range(8)]
            cpu_rows = [ft.Row(self.labels["cpu_cores"][i:i+2], spacing=self.s(8)) for i in range(0, 8, 2)]
            self.labels["uptime"] = ft.Text("Uptime: N/A", size=self.sf(9), color=ft.colors.WHITE70)
            self.labels["android_ver"] = ft.Text("Android: N/A", size=self.sf(9), color=ft.colors.WHITE70)
            self.labels["network"] = ft.Text("IP: N/A", size=self.sf(9), color=ft.colors.CYAN_200)
            self.labels["storage"] = ft.Text("Storage: N/A", size=self.sf(9), color=ft.colors.GREEN_300)

            # CPU cores + network/storage side by side
            cpu_col = ft.Column(cpu_rows, spacing=self.s(2), tight=True)
            info_col = ft.Column([
                self.labels["uptime"],
                self.labels["android_ver"],
                self.labels["network"],
                self.labels["storage"],
            ], spacing=self.s(2), tight=True)

            extended_metrics = ft.Container(
                padding=ft.padding.symmetric(horizontal=self.s(12), vertical=self.s(10)), 
                border_radius=self.s(8),
                bgcolor=ft.colors.with_opacity(0.15, ft.colors.BLACK),
                content=ft.Column([
                    ft.Row([ft.Icon(ft.icons.INSIGHTS, size=self.s(16), color=ft.colors.CYAN_400), ft.Text("EXTENDED", size=self.sf(11), weight=ft.FontWeight.BOLD, color=ft.colors.CYAN_400)], spacing=self.s(6)),
                    ft.Divider(height=self.s(4), thickness=1, color=ft.colors.with_opacity(0.2, ft.colors.CYAN_400)),
                    fps_graph_widget,
                    ft.Row([cpu_col, ft.VerticalDivider(width=self.s(1), color=ft.colors.with_opacity(0.15, ft.colors.WHITE)), info_col], spacing=self.s(8), vertical_alignment=ft.CrossAxisAlignment.START),
                ], spacing=self.s(6), tight=True, scroll=ft.ScrollMode.AUTO)
            )

        close_btn = ft.Container(
            content=ft.IconButton(icon=ft.icons.CLOSE_ROUNDED, icon_size=self.s(18), icon_color=ft.colors.RED_300, on_click=lambda _: self.close(), tooltip="Close"),
            alignment=ft.alignment.top_right, padding=0, margin=0
        )

        content_parts = [close_btn, metrics_section]
        if quick_actions: content_parts.extend([ft.Divider(height=1, thickness=1, color=ft.colors.with_opacity(0.15, ft.colors.CYAN_400)), quick_actions])
        if screen_control: content_parts.extend([ft.Divider(height=1, thickness=1, color=ft.colors.with_opacity(0.15, ft.colors.CYAN_400)), screen_control])
        if system_control: content_parts.extend([ft.Divider(height=1, thickness=1, color=ft.colors.with_opacity(0.15, ft.colors.CYAN_400)), system_control])
        if extended_metrics: content_parts.extend([ft.Divider(height=1, thickness=1, color=ft.colors.with_opacity(0.15, ft.colors.CYAN_400)), extended_metrics])

        root = ft.Container(
            padding=0, border_radius=self.s(12),
            gradient=ft.LinearGradient(begin=ft.alignment.top_center, end=ft.alignment.bottom_center, colors=[ft.colors.with_opacity(0.92, ft.colors.BLACK), ft.colors.with_opacity(0.88, ft.colors.BLUE_GREY_900)]),
            border=ft.border.all(2, ft.colors.with_opacity(0.4, ft.colors.CYAN_600)),
            shadow=ft.BoxShadow(spread_radius=self.s(2), blur_radius=self.s(20), color=ft.colors.with_opacity(0.4, ft.colors.CYAN_900), offset=ft.Offset(0, self.s(4))),
            content=ft.Stack([ft.Column(content_parts[1:], spacing=0, tight=True, scroll=ft.ScrollMode.AUTO), close_btn], expand=True)
        )
        page.add(root)
        
        # Start Threads
        threading.Thread(target=self._update_metrics_loop, daemon=True).start()
        threading.Thread(target=self._read_fps_socket_loop, daemon=True).start() # Read from socket
        threading.Thread(target=self._fps_graph_loop, daemon=True).start() # Smooth graph update
        threading.Thread(target=self._check_scrcpy_alive, daemon=True).start()

    def _create_fps_bars(self):
        self.fps_bars = []
        for _ in range(30):
            self.fps_bars.append(ft.Container(width=self.s(3), height=0, bgcolor=ft.colors.CYAN_400, border_radius=1, animate=ft.Animation(100, "easeOut")))

    def _update_fps_bars(self):
        if not self.fps_bars or len(self.fps_bars) != 30: return
        max_fps = 120
        max_height = self.s(35)
        for i, bar in enumerate(self.fps_bars):
            if i < len(self.fps_history):
                fps_val = self.fps_history[i]
                height = min(max_height, (fps_val / max_fps) * max_height)
                bar.height = max(2, height)
            else:
                bar.height = 2

    def _check_scrcpy_alive(self):
        """Monitor scrcpy process and close panel when scrcpy exits"""
        time.sleep(2)
        pid_file = os.path.join(tempfile.gettempdir(), f"scrcpy_pid_{self.serial}.txt")
        scrcpy_pid = None
        for _ in range(10):
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, "r") as f: scrcpy_pid = int(f.read().strip())
                    break
                except: pass
            time.sleep(0.3)
        
        consecutive_not_found = 0
        while self.running and not self.closing:
            try:
                found = False
                if scrcpy_pid:
                    try:
                        proc = psutil.Process(scrcpy_pid)
                        if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE: found = True
                    except: found = False
                else:
                    for proc in psutil.process_iter(['name']):
                        if self.closing: break
                        if 'scrcpy' in proc.info.get('name', '').lower():
                            found = True
                            break
                if not found:
                    consecutive_not_found += 1
                    if consecutive_not_found >= 2:
                        self.close()
                        break
                else:
                    consecutive_not_found = 0
            except: pass
            time.sleep(0.5)

    def close(self):
        if self.closing: return
        self.closing = True
        self.running = False
        
        try:
            if self.page:
                self.page.window.prevent_close = False
                self.page.window.close()
        except: pass
        
        if self.is_overlay:
            def force_exit():
                time.sleep(0.2)
                os._exit(0)
            threading.Thread(target=force_exit, daemon=True).start()

    def _read_fps_socket_loop(self):
        """Connects to the main process socket to receive FPS data"""
        if not self.ipc_port: return

        try:
            # Connect to server
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Retrying connection for a few seconds
            connected = False
            for _ in range(10):
                try:
                    sock.connect(('127.0.0.1', int(self.ipc_port)))
                    connected = True
                    break
                except:
                    time.sleep(0.5)
            
            if not connected: return

            # Read stream
            file_obj = sock.makefile('r', encoding='utf-8')
            
            while self.running and not self.closing:
                line = file_obj.readline()
                if not line: # Server closed = scrcpy exited
                    self.close()
                    break
                try:
                    val = float(line.strip())
                    self._update_fps_ui(val)
                except ValueError:
                    pass
        except Exception:
            self.close()  # Socket broke unexpectedly - scrcpy likely exited
        finally:
            try: sock.close()
            except: pass

    def _update_fps_ui(self, val):
        self.current_fps = f"{val:.1f}"
        if "fps" in self.labels: 
            self.labels["fps"].value = f"FPS: {self.current_fps}"
        if self.page and not self.closing: 
            self.page.update()

    def _fps_graph_loop(self):
        """Background thread: Adds current FPS to history every 100ms for smooth graphing"""
        while self.running and not self.closing:
            if self.mode == "extended" and self.fps_bars:
                try:
                    val = float(self.current_fps)
                    self.fps_history.append(val)
                    self._update_fps_bars()
                    if self.page and not self.closing:
                        self.page.update()
                except Exception:
                    pass
            time.sleep(0.1)

    def run_adb_instant(self, args):
        if self.closing: return
        try:
            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW
            subprocess.Popen([ADB, "-s", self.serial, "shell"] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo, creationflags=creationflags)
        except: pass

    def run_adb_output(self, args):
        if self.closing: return "", ""
        try:
            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW
            r = subprocess.run([ADB, "-s", self.serial, "shell"] + args, capture_output=True, text=True, timeout=3, startupinfo=startupinfo, creationflags=creationflags)
            return r.stdout.strip(), r.stderr.strip()
        except: return "", ""

    def run_adb_wait(self, args):
        """Like run_adb_instant but waits for completion - use for settings commands"""
        if self.closing: return
        try:
            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW
            subprocess.run([ADB, "-s", self.serial, "shell"] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, startupinfo=startupinfo, creationflags=creationflags)
        except: pass

    # ADB commands
    def press_home(self): self.run_adb_instant(["input", "keyevent", "KEYCODE_HOME"])
    def press_back(self): self.run_adb_instant(["input", "keyevent", "KEYCODE_BACK"])
    def press_recent(self): self.run_adb_instant(["input", "keyevent", "KEYCODE_APP_SWITCH"])
    def press_power(self): self.run_adb_instant(["input", "keyevent", "KEYCODE_POWER"])
    def volume_up(self): self.run_adb_instant(["input", "keyevent", "KEYCODE_VOLUME_UP"])
    def volume_down(self): self.run_adb_instant(["input", "keyevent", "KEYCODE_VOLUME_DOWN"])
    
    def take_screenshot(self):
        def _s():
            try:
                d = os.path.join(os.path.expanduser("~"), "Videos", "scrcpy_ui", "screenshots")
                os.makedirs(d, exist_ok=True)
                t = f"/sdcard/sc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                l = os.path.join(d, os.path.basename(t))
                subprocess.run([ADB, "-s", self.serial, "shell", "screencap", "-p", t], creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                subprocess.run([ADB, "-s", self.serial, "pull", t, l], creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                subprocess.run([ADB, "-s", self.serial, "shell", "rm", t], creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            except: pass
        threading.Thread(target=_s, daemon=True).start()

    def toggle_zoom(self):
        def _z():
            try:
                w, h = self._get_screen_size()
                self.run_adb_instant(["input", "tap", str(w//2), str(h//2)])
                time.sleep(0.1)
                self.run_adb_instant(["input", "tap", str(w//2), str(h//2)])
            except: pass
        threading.Thread(target=_z, daemon=True).start()

    def toggle_rotation(self): 
        def _r():
            try:
                out, _ = self.run_adb_output(["settings", "get", "system", "user_rotation"])
                new_val = "1" if out.strip() == "0" else "0"               
                self.run_adb_instant(["settings", "put", "system", "user_rotation", new_val])
            except: pass
        threading.Thread(target=_r, daemon=True).start()

    def toggle_autorotation(self):
        def _a():
            try:
                out, _ = self.run_adb_output(["settings", "get", "system", "accelerometer_rotation"])
                new_val = "0" if out.strip() == "1" else "1"
                self.run_adb_instant(["settings", "put", "system", "accelerometer_rotation", new_val])
            except: pass
        threading.Thread(target=_a, daemon=True).start()

    def media_play_pause(self): self.run_adb_instant(["input", "keyevent", "KEYCODE_MEDIA_PLAY_PAUSE"])
    def media_next(self): self.run_adb_instant(["input", "keyevent", "KEYCODE_MEDIA_NEXT"])
    def media_previous(self): self.run_adb_instant(["input", "keyevent", "KEYCODE_MEDIA_PREVIOUS"])
    def mute_volume(self): self.run_adb_instant(["input", "keyevent", "KEYCODE_VOLUME_MUTE"])
    def clear_recent_apps(self): self.run_adb_instant(["am", "clear-recent-apps"])

    def toggle_dnd(self):
        def _d():
            try:
                self._dnd_active = not getattr(self, '_dnd_active', False)
                if self._dnd_active:
                    self.run_adb_wait(["cmd", "notification", "set_dnd", "on"])
                else:
                    self.run_adb_wait(["cmd", "notification", "set_dnd", "off"])
            except: pass
        threading.Thread(target=_d, daemon=True).start()

    def _screenshot_with_flash(self, container):
        def _flash():
            try:
                container.bgcolor = ft.colors.with_opacity(0.5, ft.colors.PURPLE_300)
                if self.page: self.page.update()
                self.take_screenshot()
                time.sleep(0.15)
                container.bgcolor = ft.colors.with_opacity(0.08, ft.colors.WHITE)
                if self.page: self.page.update()
            except: pass
        threading.Thread(target=_flash, daemon=True).start()

    def _get_screen_size(self):
        """Returns (w, h) from adb wm size, fallback 1080x1920"""
        try:
            o, _ = self.run_adb_output(["wm", "size"])
            if "Physical size:" in o:
                s = o.split("Physical size:")[1].strip()
                if "x" in s:
                    w, h = map(int, s.split("x"))
                    return w, h
        except: pass
        return 1080, 1920

    def swipe_up(self):
        def _s():
            try:
                w, h = self._get_screen_size()
                self.run_adb_instant(["input", "swipe", str(w//2), str(int(h*0.7)), str(w//2), str(int(h*0.3)), "150"])
            except: pass
        threading.Thread(target=_s, daemon=True).start()

    def swipe_down(self):
        def _s():
            try:
                w, h = self._get_screen_size()
                self.run_adb_instant(["input", "swipe", str(w//2), str(int(h*0.3)), str(w//2), str(int(h*0.7)), "150"])
            except: pass
        threading.Thread(target=_s, daemon=True).start()

    def swipe_left(self):
        def _s():
            try:
                w, h = self._get_screen_size()
                self.run_adb_instant(["input", "swipe", str(int(w*0.8)), str(h//2), str(int(w*0.2)), str(h//2), "150"])
            except: pass
        threading.Thread(target=_s, daemon=True).start()

    def swipe_right(self):
        def _s():
            try:
                w, h = self._get_screen_size()
                self.run_adb_instant(["input", "swipe", str(int(w*0.2)), str(h//2), str(int(w*0.8)), str(h//2), "150"])
            except: pass
        threading.Thread(target=_s, daemon=True).start()

    def _update_metrics_loop(self):
        threading.Thread(target=self._update_static_info, daemon=True).start()
        while self.running and not self.closing:
            try:
                if not self.page or self.closing: break
                self._scan_thermal_zones()
                if "cpu" in self.labels: self._update_cpu_display()
                if "gpu" in self.labels: self._update_gpu_display()
                if self.update_counter % 4 == 0 and "ram" in self.labels: self._update_ram()
                if self.update_counter % 3 == 0 and "brightness" in self.labels: self._update_brightness()
                if self.update_counter % 5 == 0 and "battery" in self.labels: self._update_battery_reliable()
                if self.mode == "extended" and self.update_counter % 5 == 0 and "cpu_cores" in self.labels: self._update_cpu_cores()
                if self.page and not self.closing: self.page.update()
                self.update_counter += 1
                time.sleep(1)
            except: time.sleep(1)

    def _scan_thermal_zones(self):
        try:
            out, _ = self.run_adb_output(["cat /sys/class/thermal/thermal_zone*/type; echo '|SEP|'; cat /sys/class/thermal/thermal_zone*/temp"])
            if "|SEP|" in out:
                parts = out.split("|SEP|")
                temps = parts[1].strip().splitlines()
                max_temp = 0
                for t in temps:
                    if t.strip().isdigit():
                        val = int(t.strip())
                        if val > 1000: val /= 1000
                        if 30 <= val <= 110 and val > max_temp: max_temp = val
                self.current_soc_temp = max_temp if max_temp > 0 else None
        except: self.current_soc_temp = None

    def _update_cpu_display(self):
        load_txt = "N/A"
        try:
            out, _ = self.run_adb_output(["cat", "/proc/stat"])
            lines = out.splitlines()
            if lines and lines[0].startswith("cpu "):
                parts = lines[0].split()
                if len(parts) >= 5:
                    user, nice, system, idle = map(int, parts[1:5])
                    total = user + nice + system + idle
                    active = user + nice + system
                    if self.last_cpu_stats:
                        dt, da = total - self.last_cpu_stats[0], active - self.last_cpu_stats[1]
                        if dt > 0: load_txt = f"{(da / dt) * 100:.0f}%"
                    self.last_cpu_stats = (total, active)
        except: pass
        temp_txt = f" {self.current_soc_temp:.0f}°C" if self.current_soc_temp else ""
        self.labels["cpu"].value = f"{load_txt}{temp_txt}"

    def _update_gpu_display(self):
        txt = self.cached_gpu_model
        if self.current_soc_temp: txt += f" {self.current_soc_temp:.0f}°C"
        self.labels["gpu"].value = txt

    def _update_brightness(self):
        try:
            out, _ = self.run_adb_output(["settings", "get", "system", "screen_brightness"])
            if out.strip().isdigit(): self.labels["brightness"].value = f"{int(int(out.strip())/255*100)}%"
            else: self.labels["brightness"].value = "N/A"
        except: pass

    def _update_ram(self):
        try:
            out, _ = self.run_adb_output(["cat", "/proc/meminfo"])
            total, avail = 0, 0
            for line in out.splitlines():
                if "MemTotal:" in line: total = int(line.split()[1]) / 1024 / 1024
                if "MemAvailable:" in line: avail = int(line.split()[1]) / 1024 / 1024
            if total > 0: self.labels["ram"].value = f"{total-avail:.1f}/{total:.1f}GB"
        except: pass

    def _update_battery_reliable(self):
        try:
            out, _ = self.run_adb_output(["dumpsys", "battery"])
            lvl, volt, charging = None, None, False
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("level:"): lvl = line.split(":")[1].strip()
                elif line.startswith("voltage:"):
                    try: volt = int(line.split(":")[1].strip()); volt = volt / 1000 if volt > 100000 else volt
                    except: pass
                elif "AC powered: true" in line or "USB powered: true" in line: charging = True
            if lvl:
                txt = f"{lvl}%" + (f" ({volt/1000:.1f}V)" if volt else "")
                self.labels["battery"].value = txt
                if "charging" in self.labels: self.labels["charging"].visible = charging
        except: pass

    def _update_cpu_cores(self):
        try:
            out, _ = self.run_adb_output(["cat", "/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"])
            for i, val in enumerate(out.strip().splitlines()):
                if i < 8 and val.isdigit(): self.labels["cpu_cores"][i].value = f"C{i}: {int(val)/1000:.0f}MHz"
        except: pass

    def _update_static_info(self):
        try:
            out, _ = self.run_adb_output(["dumpsys SurfaceFlinger | grep GLES"])
            if "GLES:" in out:
                parts = out.split(",")
                for part in parts:
                    clean = part.replace("GLES:", "").replace("(TM)", "").strip()
                    if any(x in clean for x in ["Adreno", "Mali", "PowerVR", "NVIDIA"]):
                        self.cached_gpu_model = clean; break
            else: self.cached_gpu_model = "Unknown GPU"
        except: self.cached_gpu_model = "Unknown GPU"
        while self.running and not self.closing:
            try:
                if "uptime" in self.labels:
                    out, _ = self.run_adb_output(["uptime", "-p"])
                    if out: self.labels["uptime"].value = f"Up: {out.replace('up ', '').replace('hours', 'h').replace('minutes', 'm')}"
                if "android_ver" in self.labels:
                    out, _ = self.run_adb_output(["getprop", "ro.build.version.release"])
                    if out: self.labels["android_ver"].value = f"Android {out}"
                if "network" in self.labels:
                    out, _ = self.run_adb_output(["ip", "route"])
                    ip = "N/A"
                    for line in out.splitlines():
                        if "src" in line:
                            parts = line.split()
                            idx = parts.index("src") if "src" in parts else -1
                            if idx != -1 and idx + 1 < len(parts):
                                ip = parts[idx + 1]; break
                    self.labels["network"].value = f"IP: {ip}"
                if "storage" in self.labels:
                    out, _ = self.run_adb_output(["df", "/data"])
                    for line in out.splitlines():
                        if "/data" in line:
                            parts = line.split()
                            if len(parts) >= 4:
                                try:
                                    total = int(parts[1]) / 1024 / 1024
                                    avail = int(parts[3]) / 1024 / 1024
                                    used = total - avail
                                    self.labels["storage"].value = f"Storage: {used:.1f}/{total:.1f}GB"
                                except: pass
                            break
                time.sleep(30)
            except: time.sleep(30)

def _launch_panel_if_requested():
    """Handle --flet-panel argument. Called both from script and frozen EXE."""
    if len(sys.argv) > 1 and sys.argv[1] == "--flet-panel":
        serial = sys.argv[2] if len(sys.argv) > 2 else None
        mode = sys.argv[3] if len(sys.argv) > 3 else "standard"
        port = sys.argv[4] if len(sys.argv) > 4 else None

        if serial:
            try:
                panel = AdvancedControlPanel(serial, mode=mode, is_overlay=True, ipc_port=port)
                ft.app(target=panel._main)
            except:
                pass
        sys.exit(0)

# Works in both normal script and PyInstaller EXE
if __name__ == "__main__" or getattr(sys, 'frozen', False):
    _launch_panel_if_requested()