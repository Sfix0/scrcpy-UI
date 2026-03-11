"""
File Manager for scrcpy UI
Advanced file browser with dynamic toolbar and inline editing
Version: 3.0 - Modern UX with enhanced visuals and animations
"""

import flet as ft
import subprocess
import threading
import os
import sys
import tempfile
import time
from datetime import datetime

# Storage fallback values
DEFAULT_STORAGE_TOTAL_GB = 128.0
DEFAULT_STORAGE_USED_GB = 119.6


class FileManager:
    """File Manager for Android devices via ADB"""
    
    # UI States
    STATE_EMPTY = 0
    STATE_SINGLE = 1
    STATE_MULTIPLE = 2
    STATE_RENAME = 3
    STATE_DELETE_CONFIRM = 4
    STATE_NEW_FOLDER = 5
    
    def __init__(self, page: ft.Page, serial: str, device_name: str = "Device", lang=None):
        self.page = page
        self.serial = serial
        self.device_name = device_name
        self.lang = lang
        self.current_path = "/storage/emulated/0"
        self.selected_files = set()
        self.files_data = []
        self.temp_files = []
        self.clipboard_files = []
        self.clipboard_operation = None
        self.current_state = self.STATE_EMPTY
        
        # Selection mode
        self.selection_mode = False
        
        # Navigation history
        self.navigation_history = []
        self.history_index = -1
        
        # Inline editing state
        self.rename_file_data = None
        self.new_folder_active = False
        
        # UI references
        self.dialog = None
        self.files_container = None
        self.breadcrumbs_container = None
        self.toolbar_actions = None
        self.status_text = None
        self.storage_bar = None
        self.storage_text = None
        self.storage_percent = None
        self.progress_container = None
        self.progress_text = None
        self.progress_percent = None
        self.progress_bar = None
        self.file_picker = None
        self.folder_picker = None
        self.pending_downloads = []
        
        # Info panel state
        self.info_bottom_sheet = None  # BottomSheet for file info
        
        
        # Breadcrumbs state
        self._dialog_width = 860  # fallback
        
        # Theme cache
        self._theme_cache = None
        self._last_theme_mode = None
    
    def _close_btn(self):
        """Animated close button: rotates 90° and turns red on hover."""
        is_light = self.page.theme_mode != ft.ThemeMode.DARK
        base = ft.colors.BLACK if is_light else ft.colors.WHITE
        icon = ft.Icon(ft.icons.CLOSE, size=20, color=ft.colors.with_opacity(0.5, base))
        def on_hover(e):
            e.control.rotate = ft.Rotate(angle=1.5708 if e.data == "true" else 0, alignment=ft.alignment.center)
            icon.color = ft.colors.RED_400 if e.data == "true" else ft.colors.with_opacity(0.5, base)
            self.page.update()
        return ft.Container(
            content=icon, width=32, height=32, border_radius=16,
            alignment=ft.alignment.center, ink=True,
            rotate=ft.Rotate(angle=0, alignment=ft.alignment.center),
            animate_rotation=ft.Animation(250, ft.AnimationCurve.EASE_IN_OUT),
            on_click=lambda _: self.close_file_manager(), on_hover=on_hover,
        )

    def t(self, key, **kwargs):
        """Get translated string with optional format arguments"""
        if self.lang is None:
            return key
        
        result = self.lang.t(key)
        
        if kwargs and result != key:
            try:
                result = result.format(**kwargs)
            except (KeyError, IndexError):
                pass
        
        return result
        
    # ==================== THEME SYSTEM ====================
    
    def get_theme(self):
        """Get theme colors with caching"""
        current_mode = self.page.theme_mode
        if self._theme_cache is None or self._last_theme_mode != current_mode:
            self._last_theme_mode = current_mode
            self._theme_cache = self._build_theme(current_mode)
        return self._theme_cache
    
    def _build_theme(self, theme_mode):
        """Build theme dictionary (internal helper)"""
        is_dark = theme_mode == ft.ThemeMode.DARK
        return {
            # Unified background
            'bg': ft.colors.GREY_900 if is_dark else ft.colors.GREY_50,
            'card': ft.colors.GREY_900 if is_dark else ft.colors.GREY_50,
            
            # Subtle toolbar
            'toolbar': ft.colors.TRANSPARENT,
            'toolbar_border': ft.colors.with_opacity(0.15, ft.colors.GREY_700 if is_dark else ft.colors.GREY_400),
            
            # Text
            'text': ft.colors.WHITE if is_dark else ft.colors.GREY_900,
            'text_secondary': ft.colors.GREY_400 if is_dark else ft.colors.GREY_600,
            'text_muted': ft.colors.GREY_600 if is_dark else ft.colors.GREY_500,
            
            # Interactive states with hover effect
            'hover': ft.colors.with_opacity(0.08, ft.colors.WHITE if is_dark else ft.colors.BLACK),
            'selected': ft.colors.with_opacity(0.15, ft.colors.BLUE),
            'selected_border': ft.colors.with_opacity(0.4, ft.colors.BLUE),
            
            # Accent colors
            'accent': ft.colors.BLUE_500,
            'accent_hover': ft.colors.BLUE_600,
            
            # Progress bars with gradient
            'progress_bg': ft.colors.with_opacity(0.15, ft.colors.GREY_600 if is_dark else ft.colors.GREY_400),
            'progress_fill': ft.colors.BLUE_500,
            
            # Special states
            'rename_bg': ft.colors.with_opacity(0.1, ft.colors.BLUE),
            'rename_border': ft.colors.BLUE_500,
            'delete_bg': ft.colors.with_opacity(0.1, ft.colors.RED),
            'delete_border': ft.colors.RED_500,
            'create_bg': ft.colors.with_opacity(0.1, ft.colors.GREEN),
            'create_border': ft.colors.GREEN_500,
            
            # Dividers
            'divider': ft.colors.with_opacity(0.15, ft.colors.GREY_600 if is_dark else ft.colors.GREY_400),
        }
    
    # ==================== FILE TYPE CONSTANTS ====================
    
    FILE_TYPE_EXTENSIONS = {
        'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic'],
        'video': ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm'],
        'audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'],
        'archive': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'],
        'document': ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt'],
    }
    
    # ==================== HELPER METHODS ====================
    
    def _get_subprocess_config(self):
        """Get subprocess configuration for hiding console on Windows"""
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
        return startupinfo, creationflags
    
    def _escape_path(self, path):
        """Escape special characters in file path for shell commands"""
        return (path
            .replace('(', '\\(')
            .replace(')', '\\)')
            .replace(' ', '\\ ')
            .replace("'", "\\'"))
    
    # ==================== ADB OPERATIONS ====================
    
    def run_adb(self, args, timeout=10):
        """Execute ADB command and return output with hidden console"""
        try:
            cmd = ["adb", "-s", self.serial, "shell"] + args
            startupinfo, creationflags = self._get_subprocess_config()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=timeout,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            return result.stdout.strip(), result.stderr.strip()
        except Exception as e:
            return "", str(e)

    def run_adb_shell_string(self, shell_cmd, timeout=10):
        """Execute ADB shell command as a single string (handles paths with spaces)"""
        try:
            cmd = ["adb", "-s", self.serial, "shell", shell_cmd]
            startupinfo, creationflags = self._get_subprocess_config()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=timeout,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            return result.stdout.strip(), result.stderr.strip()
        except Exception as e:
            return "", str(e)

    def list_files(self, path):
        """List files in directory using ls -la"""
        out, err = self.run_adb_shell_string(f'ls -la "{path}"', timeout=30)
        if not out:
            return []
        
        files = []
        for line in out.splitlines():
            parsed = self.parse_ls_line(line, path)
            if parsed:
                files.append(parsed)
        
        files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return files
    
    def parse_ls_line(self, line, parent_path):
        """Parse ls -la output line"""
        parts = line.split()
        if len(parts) < 8:
            return None
        
        permissions = parts[0]
        name = ' '.join(parts[7:])
        
        if name in ['.', '..']:
            return None
        
        is_dir = permissions.startswith('d')
        size_bytes = int(parts[4]) if parts[4].isdigit() else 0
        
        # Store full date for info panel
        full_date = self.format_full_date_from_ls_parts(parts[5], parts[6])
        
        try:
            date_str = f"{parts[5]} {parts[6]}"
            modified = self.format_date(date_str)
        except:
            modified = self.t("fm_unknown")
        
        file_path = os.path.join(parent_path, name).replace('\\', '/')
        
        return {
            'name': name,
            'is_dir': is_dir,
            'size': size_bytes,
            'modified': modified,
            'full_date': full_date,
            'path': file_path,
            'type': self.get_file_type(name, is_dir)
        }
    
    def format_full_date_from_ls_parts(self, month_str, day_time_str):
        """Format date from ls -la parts to full format YYYY-MM-DD HH:MM"""
        # Check if it's Android format (YYYY-MM-DD HH:MM)
        if '-' in month_str and len(month_str) == 10:
            # Already in YYYY-MM-DD format
            if ':' in day_time_str:
                return f"{month_str} {day_time_str}"
            else:
                return month_str
        
        current_year = datetime.now().year
        
        months = {
            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
        }
        
        if month_str in months:
            month = months[month_str]
            if ':' in day_time_str:
                return f"{current_year}-{month}-{day_time_str}"
            else:
                return f"{current_year}-{month}-{day_time_str.zfill(2)}"
        
        return self.t("fm_unknown")
    
    def format_date(self, date_str):
        """Format date to MM.YYYY format"""
        formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).strftime("%m.%Y")
            except ValueError:
                continue
        return self.t("fm_unknown")
    
    def format_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
    
    def get_file_type(self, name, is_dir):
        """Determine file type from extension"""
        if is_dir:
            return 'folder'
        
        ext = os.path.splitext(name)[1].lower()
        
        for file_type, extensions in self.FILE_TYPE_EXTENSIONS.items():
            if ext in extensions:
                return file_type
        
        return 'unknown'
    
    def get_storage_info(self):
        """Get storage information using df"""
        out, _ = self.run_adb(["df", "/storage/emulated/0"])
        
        lines = out.splitlines()
        if len(lines) < 2:
            return DEFAULT_STORAGE_TOTAL_GB, DEFAULT_STORAGE_USED_GB
        
        parts = lines[1].split()
        if len(parts) < 4:
            return DEFAULT_STORAGE_TOTAL_GB, DEFAULT_STORAGE_USED_GB
        
        try:
            total_kb = int(parts[1])
            used_kb = int(parts[2])
            total_gb = total_kb / 1024 / 1024
            used_gb = used_kb / 1024 / 1024
            return total_gb, used_gb
        except:
            return DEFAULT_STORAGE_TOTAL_GB, DEFAULT_STORAGE_USED_GB
    
    def _run_adb_transfer(self, args, timeout=300):
        """Run adb pull/push transfer command with hidden console"""
        try:
            startupinfo, creationflags = self._get_subprocess_config()
            result = subprocess.run(
                ["adb", "-s", self.serial] + args,
                capture_output=True, text=True,
                encoding='utf-8', errors='ignore',
                timeout=timeout,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            return result.returncode == 0
        except Exception:
            return False

    def pull_file(self, phone_path, local_path):
        """Download file from phone to PC"""
        return self._run_adb_transfer(["pull", phone_path, local_path])

    def push_file(self, local_path, phone_path):
        """Upload file from PC to phone"""
        return self._run_adb_transfer(["push", local_path, phone_path])
    
    def delete_file(self, path, is_dir=False):
        """Delete file or folder"""
        path_escaped = self._escape_path(path)
        
        if is_dir:
            self.run_adb(["rm", "-rf", path_escaped])
        else:
            self.run_adb(["rm", "-f", path_escaped])
    
    def create_folder(self, path):
        """Create new folder"""
        self.run_adb(["mkdir", "-p", path])
    
    def rename_file(self, old_path, new_name):
        """Rename file or folder"""
        parent = os.path.dirname(old_path)
        new_path = os.path.join(parent, new_name).replace('\\', '/')
        
        old_path_escaped = self._escape_path(old_path)
        new_path_escaped = self._escape_path(new_path)
        
        self.run_adb(["mv", old_path_escaped, new_path_escaped])
        return new_path
    
    def copy_file_on_phone(self, source, dest):
        """Copy file on phone"""
        source_escaped = self._escape_path(source)
        dest_escaped = self._escape_path(dest)
        
        self.run_adb(["cp", "-r", source_escaped, dest_escaped])
    
    def move_file_on_phone(self, source, dest):
        """Move file on phone"""
        source_escaped = self._escape_path(source)
        dest_escaped = self._escape_path(dest)
        
        self.run_adb(["mv", source_escaped, dest_escaped])
    
    # ==================== FILE OPERATIONS ====================
    
    def open_file_or_folder(self, file_data):
        """Open file or navigate to folder"""
        if file_data['is_dir']:
            self.navigate_to(file_data['path'])
        else:
            self.open_file(file_data)
    
    def open_file(self, file_data):
        """Open file - pull to temp and open with system default"""
        def _open():
            try:
                self.show_progress(self.t("fm_opening", filename=file_data['name']), 30)
                
                ext = os.path.splitext(file_data['name'])[1]
                temp_file = tempfile.mktemp(suffix=ext)
                
                self.show_progress(self.t("fm_downloading", filename=file_data['name']), 60)
                
                if self.pull_file(file_data['path'], temp_file):
                    self.temp_files.append(temp_file)
                    self.show_progress(self.t("fm_opening", filename=file_data['name']), 90)
                    
                    if os.name == 'nt':
                        os.startfile(temp_file)
                    elif os.name == 'posix':
                        subprocess.run(['xdg-open', temp_file])
                    
                    self.hide_progress()
                    self.show_snackbar(self.t("fm_opened", filename=file_data['name']))
                else:
                    self.hide_progress()
                    self.show_snackbar(self.t("fm_failed_open", filename=file_data['name']), error=True)
            except Exception as e:
                self.hide_progress()
                self.show_snackbar(self.t("fm_error", message=str(e)), error=True)
        
        threading.Thread(target=_open, daemon=True).start()
    
    def download_selected_files(self, e=None):
        """Download selected files"""
        if not self.selected_files:
            return
        
        files_to_download = [f for f in self.files_data if f['path'] in self.selected_files]
        self._download_files(files_to_download)
    
    def _download_files(self, files_to_download):
        """Internal download implementation"""
        if not files_to_download:
            return
        
        self.pending_downloads = files_to_download
        
        if not self.folder_picker:
            self.folder_picker = ft.FilePicker(on_result=self._on_folder_selected)
        
        self.page.overlay.append(self.folder_picker)
        self.show_snackbar(self.t("fm_select_folder"))
        self.folder_picker.get_directory_path()
    
    def _on_folder_selected(self, e):
        """Handle folder selection for downloads"""
        if not e.path or not self.pending_downloads:
            return
        
        folder_path = e.path
        total = len(self.pending_downloads)
        
        def _download():
            try:
                for idx, file_data in enumerate(self.pending_downloads):
                    filename = file_data['name']
                    local_path = os.path.join(folder_path, filename)
                    
                    progress = int((idx / total) * 100)
                    self.show_progress(self.t("fm_downloading_progress", filename=filename, current=idx+1, total=total), progress)
                    
                    self.pull_file(file_data['path'], local_path)
                
                self.hide_progress()
                self.show_snackbar(self.t("fm_downloaded_to", count=total, path=folder_path))
            except Exception as e:
                self.hide_progress()
                self.show_snackbar(self.t("fm_error", message=str(e)), error=True)
        
        threading.Thread(target=_download, daemon=True).start()
    
    def upload_files(self, e):
        """Upload files from PC to current phone directory"""
        if not e or not e.files:
            return
        
        files_to_upload = e.files
        
        def _upload():
            try:
                total = len(files_to_upload)
                
                for idx, file in enumerate(files_to_upload):
                    filename = os.path.basename(file.path)
                    phone_path = os.path.join(self.current_path, filename).replace('\\', '/')
                    
                    progress = int((idx / total) * 100)
                    self.show_progress(self.t("fm_uploading_progress", filename=filename, current=idx+1, total=total), progress)
                    
                    self.push_file(file.path, phone_path)
                
                self.hide_progress()
                self.refresh_files()
                self.show_snackbar(self.t("fm_uploaded", count=total))
            except Exception as e:
                self.hide_progress()
                self.show_snackbar(self.t("fm_error", message=str(e)), error=True)
        
        threading.Thread(target=_upload, daemon=True).start()
    
    # ==================== STATE MANAGEMENT ====================
    
    def update_state(self):
        """Update current state based on selection"""
        count = len(self.selected_files)
        
        if self.new_folder_active:
            self.current_state = self.STATE_NEW_FOLDER
        elif self.rename_file_data:
            self.current_state = self.STATE_RENAME
        elif count == 0:
            self.current_state = self.STATE_EMPTY
        elif count == 1:
            self.current_state = self.STATE_SINGLE
        else:
            self.current_state = self.STATE_MULTIPLE
        
        self.rebuild_toolbar()
    
    def rebuild_toolbar(self):
        """Rebuild toolbar based on current state"""
        if not self.toolbar_actions:
            return
        
        theme = self.get_theme()
        buttons = []
        
        # Navigation buttons
        buttons.append(self._create_icon_button(
            ft.icons.ARROW_BACK,
            self.t("fm_back"),
            self.navigate_back,
        ))
        buttons.append(self._create_icon_button(
            ft.icons.HOME,
            self.t("fm_home"),
            self.navigate_home,
        ))
        
        buttons.append(ft.Container(width=1, height=24, bgcolor=theme['divider']))
        
        if self.current_state == self.STATE_EMPTY:
            buttons.extend([
                self._create_icon_button(ft.icons.CHECKLIST, self.t("fm_select_mode"), lambda e: self.activate_selection_mode()),
                self._create_icon_button(ft.icons.CREATE_NEW_FOLDER, self.t("fm_new_folder"), self.start_new_folder),
                self._create_icon_button(ft.icons.UPLOAD_FILE, self.t("fm_upload"), lambda e: self.file_picker.pick_files(allow_multiple=True)),
                self._create_icon_button(ft.icons.DOWNLOAD, self.t("fm_download"), self.download_selected_files, disabled=True),
            ])
            
        elif self.current_state == self.STATE_SINGLE:
            actions_menu = self._create_actions_menu(is_single=True)
            buttons.extend([
                self._create_icon_button(ft.icons.SELECT_ALL, self.t("fm_select_all"), lambda e: self.select_all_files(), icon_color=theme['accent']),
                self._create_icon_button(ft.icons.CLOSE, self.t("fm_cancel_selection"), lambda e: self.deactivate_selection_mode()),
                ft.Container(width=1, height=24, bgcolor=theme['divider']),
                self._create_icon_button(ft.icons.INFO, self.t("fm_info"), self.show_info_panel_method),
                actions_menu,
                self._create_icon_button(ft.icons.DELETE, self.t("fm_delete"), self.delete_single_file),
            ])
            
        elif self.current_state == self.STATE_MULTIPLE:
            actions_menu = self._create_actions_menu(is_single=False)
            buttons.extend([
                self._create_icon_button(ft.icons.SELECT_ALL, self.t("fm_select_all"), lambda e: self.select_all_files(), icon_color=theme['accent']),
                self._create_icon_button(ft.icons.CLOSE, self.t("fm_cancel_selection"), lambda e: self.deactivate_selection_mode()),
                ft.Container(width=1, height=24, bgcolor=theme['divider']),
                actions_menu,
                self._create_icon_button(ft.icons.DELETE, self.t("fm_delete"), self.start_delete_multiple),
            ])
            
        elif self.current_state == self.STATE_DELETE_CONFIRM:
            count = len(self.selected_files)
            buttons = [
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.icons.WARNING_AMBER_ROUNDED, size=20, color=ft.colors.RED_400),
                        ft.Text(self.t("fm_delete_confirm", count=count), size=13, color=ft.colors.RED_400, weight=ft.FontWeight.W_500),
                        ft.IconButton(
                            icon=ft.icons.CHECK_CIRCLE,
                            icon_size=20,
                            icon_color=ft.colors.RED_400,
                            on_click=self.confirm_delete_multiple,
                        ),
                        ft.IconButton(
                            icon=ft.icons.CANCEL,
                            icon_size=20,
                            on_click=self.cancel_delete,
                        ),
                    ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
                    bgcolor=theme['delete_bg'],
                    border=ft.border.all(1, theme['delete_border']),
                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    border_radius=8,
                    expand=True,
                    animate=ft.Animation(200, ft.AnimationCurve.EASE_IN_OUT),
                )
            ]
        
        # Paste button
        if self.clipboard_files and self.current_state in [self.STATE_EMPTY, self.STATE_SINGLE, self.STATE_MULTIPLE]:
            buttons.append(ft.Container(width=1, height=24, bgcolor=theme['divider']))
            buttons.append(self._create_icon_button(
                ft.icons.CONTENT_PASTE,
                self.t("fm_paste_count", count=len(self.clipboard_files)),
                self.paste_files,
                icon_color=theme['accent']
            ))
        
        self.toolbar_actions.controls = buttons
        self.page.update()
    
    def _create_actions_menu(self, is_single: bool):
        """Create accented PopupMenuButton for file actions"""
        theme = self.get_theme()
        items = []
        if is_single:
            items.append(ft.PopupMenuItem(text=self.t("fm_rename"), icon=ft.icons.EDIT, on_click=self.start_rename))
        items.append(ft.PopupMenuItem(text=self.t("fm_copy"),     icon=ft.icons.CONTENT_COPY, on_click=self.copy_selected))
        items.append(ft.PopupMenuItem(text=self.t("fm_cut"),      icon=ft.icons.CONTENT_CUT,  on_click=self.cut_selected))
        items.append(ft.PopupMenuItem(text=self.t("fm_download"), icon=ft.icons.DOWNLOAD,     on_click=self.download_selected_files))

        return ft.PopupMenuButton(
            items=items,
            content=ft.Container(
                content=ft.Icon(ft.icons.MORE_VERT, size=20, color=theme["accent"]),
                bgcolor=ft.colors.with_opacity(0.12, theme["accent"]),
                border_radius=8,
                padding=ft.padding.all(6),
                border=ft.border.all(1, ft.colors.with_opacity(0.35, theme["accent"])),
            ),
        )

    def _create_icon_button(self, icon, text, on_click, disabled=False, icon_color=None):
        """Create styled icon button with hover effect"""
        theme = self.get_theme()
        
        btn = ft.IconButton(
            icon=icon,
            icon_size=20,
            tooltip=text,
            icon_color=icon_color or (theme['text_secondary'] if disabled else theme['text']),
            on_click=on_click,
            disabled=disabled,
        )
        
        # Простий wrapper без анімації для стабільності
        return btn
    
    # ==================== INLINE EDITING ====================
    
    def start_new_folder(self, e=None):
        """Start creating new folder inline"""
        self.new_folder_active = True
        self.update_state()
        self.rebuild_file_list()
    
    def confirm_new_folder(self, folder_name):
        """Confirm new folder creation"""
        if folder_name.strip():
            try:
                folder_path = os.path.join(self.current_path, folder_name).replace('\\', '/')
                self.create_folder(folder_path)
                self.show_snackbar(self.t("fm_created", folder_name=folder_name))
            except Exception as ex:
                self.show_snackbar(self.t("fm_error", message=str(ex)), error=True)
        
        self.new_folder_active = False
        self.refresh_files()
    
    def cancel_new_folder(self):
        """Cancel new folder creation"""
        self.new_folder_active = False
        self.update_state()
        self.rebuild_file_list()
    
    def start_rename(self, e=None):
        """Start renaming selected file inline"""
        if len(self.selected_files) == 1:
            file_path = list(self.selected_files)[0]
            self.rename_file_data = next((f for f in self.files_data if f['path'] == file_path), None)
            self.update_state()
            self.rebuild_file_list()
    
    def confirm_rename(self, new_name):
        """Confirm file rename"""
        if self.rename_file_data and new_name.strip() and new_name != self.rename_file_data['name']:
            try:
                self.rename_file(self.rename_file_data['path'], new_name)
                self.show_snackbar(self.t("fm_renamed", filename=new_name))
            except Exception as ex:
                self.show_snackbar(self.t("fm_error", message=str(ex)), error=True)
        
        self.rename_file_data = None
        self.refresh_files()
    
    def cancel_rename(self):
        """Cancel file rename"""
        self.rename_file_data = None
        self.update_state()
        self.rebuild_file_list()
    
    def delete_single_file(self, e=None):
        """Delete single selected file"""
        if len(self.selected_files) == 1:
            self.start_delete_multiple()
    
    def start_delete_multiple(self, e=None):
        """Start delete confirmation"""
        if e and hasattr(e, 'stop_propagation'):
            e.stop_propagation()
        
        if self.current_state == self.STATE_DELETE_CONFIRM:
            return
        
        self.current_state = self.STATE_DELETE_CONFIRM
        self.rebuild_toolbar()
    
    def confirm_delete_multiple(self, e=None):
        """Confirm deletion"""
        selected_data = [f for f in self.files_data if f['path'] in self.selected_files]
        
        def _delete():
            try:
                total = len(selected_data)
                for idx, file_data in enumerate(selected_data):
                    progress = int((idx / total) * 100)
                    self.show_progress(self.t("fm_deleting_progress", current=idx+1, total=total), progress)
                    self.delete_file(file_data['path'], file_data['is_dir'])
                
                self.hide_progress()
                self.selected_files.clear()
                self.refresh_files()
                self.show_snackbar(self.t("fm_deleted", count=total))
            except Exception as ex:
                self.hide_progress()
                self.show_snackbar(self.t("fm_error", message=str(ex)), error=True)
        
        threading.Thread(target=_delete, daemon=True).start()
    
    def cancel_delete(self, e=None):
        """Cancel deletion"""
        self.update_state()
        self.rebuild_file_list()
    
    def _clipboard_selected(self, operation: str):
        """Copy or cut selected files to clipboard"""
        if not self.selected_files:
            return
        self.clipboard_files = [f for f in self.files_data if f['path'] in self.selected_files]
        self.clipboard_operation = operation
        key = "fm_copied" if operation == 'copy' else "fm_cut_action"
        self.show_snackbar(self.t(key, count=len(self.clipboard_files)))
        self.update_state()

    def copy_selected(self, e=None):
        """Copy selected files"""
        self._clipboard_selected('copy')

    def cut_selected(self, e=None):
        """Cut selected files"""
        self._clipboard_selected('cut')
    
    def paste_files(self, e=None):
        """Paste files from clipboard"""
        if not self.clipboard_files:
            return
        
        def _paste():
            try:
                total = len(self.clipboard_files)
                
                for idx, file_data in enumerate(self.clipboard_files):
                    filename = file_data['name']
                    dest_path = os.path.join(self.current_path, filename).replace('\\', '/')
                    
                    progress = int((idx / total) * 100)
                    operation_key = "fm_moving" if self.clipboard_operation == 'cut' else "fm_copying_action"
                    self.show_progress(self.t(operation_key) + f" ({idx+1}/{total})", progress)
                    
                    if self.clipboard_operation == 'copy':
                        self.copy_file_on_phone(file_data['path'], dest_path)
                    else:
                        self.move_file_on_phone(file_data['path'], dest_path)
                
                self.hide_progress()
                self.clipboard_files.clear()
                self.clipboard_operation = None
                self.refresh_files()
                self.show_snackbar(self.t("fm_pasted", count=total))
            except Exception as e:
                self.hide_progress()
                self.show_snackbar(self.t("fm_error", message=str(e)), error=True)
        
        threading.Thread(target=_paste, daemon=True).start()
    
    # ==================== NAVIGATION ====================
    
    def navigate_to(self, path):
        """Navigate to directory and save to history"""
        self.current_path = path
        self.selected_files.clear()
        self.new_folder_active = False
        self.rename_file_data = None
        self.selection_mode = False
        
        # Додати в історію
        if self.history_index < len(self.navigation_history) - 1:
            # Видалити "майбутнє" якщо ми не в кінці історії
            self.navigation_history = self.navigation_history[:self.history_index + 1]
        
        self.navigation_history.append(path)
        self.history_index = len(self.navigation_history) - 1
        
        self.refresh_files()
    
    def navigate_back(self, e=None):
        """Navigate to parent directory"""
        if self.current_path != "/":
            parent = os.path.dirname(self.current_path)
            self.navigate_to(parent if parent else "/")
    
    def navigate_home(self, e=None):
        """Navigate to /storage/emulated/0"""
        self.navigate_to("/storage/emulated/0")
    
    def go_back(self):
        """Go to previous path in history (Mouse Button 4)"""
        if self.history_index > 0:
            self.history_index -= 1
            self.current_path = self.navigation_history[self.history_index]
            self.selected_files.clear()
            self.selection_mode = False
            self.refresh_files()
    
    def go_forward(self):
        """Go to next path in history (Mouse Button 5)"""
        if self.history_index < len(self.navigation_history) - 1:
            self.history_index += 1
            self.current_path = self.navigation_history[self.history_index]
            self.selected_files.clear()
            self.selection_mode = False
            self.refresh_files()
    
    # ==================== UI HELPERS ====================
    
    def show_snackbar(self, message, error=False):
        """Show snackbar notification"""
        self.page.snack_bar = ft.SnackBar(
            ft.Text(message),
            bgcolor=ft.colors.RED_700 if error else ft.colors.GREEN_700
        )
        self.page.snack_bar.open = True
        self.page.update()
    
    def show_progress(self, text, progress):
        """Show progress indicator"""
        if self.progress_container:
            self.progress_text.value = text
            self.progress_percent.value = f"{progress}%"
            self.progress_bar.value = progress / 100
            self.progress_container.visible = True
            self.page.update()
    
    def hide_progress(self):
        """Hide progress indicator"""
        if self.progress_container:
            self.progress_container.visible = False
            self.page.update()
            time.sleep(0.1)
    
    def get_file_tooltip(self, file_data):
        """Create tooltip text with full file information"""
        name = file_data['name']
        size = self.format_size(file_data['size']) if not file_data['is_dir'] else self.t("fm_folder_type")
        date = file_data.get('full_date', self.t("fm_unknown"))
        path = file_data['path']
        
        return f"{name}\n{self.t('fm_col_size')}: {size}\n{self.t('fm_col_date')}: {date}\n{self.t('fm_path')}: {path}"
    
    def get_file_icon(self, file_type):
        """Get icon for file type"""
        icons = {
            'folder': (ft.icons.FOLDER, ft.colors.BLUE_400),
            'image': (ft.icons.IMAGE, ft.colors.PURPLE_400),
            'video': (ft.icons.VIDEO_FILE, ft.colors.PINK_400),
            'audio': (ft.icons.AUDIO_FILE, ft.colors.GREEN_400),
            'archive': (ft.icons.FOLDER_ZIP, ft.colors.ORANGE_400),
            'document': (ft.icons.DESCRIPTION, ft.colors.RED_400),
            'unknown': (ft.icons.INSERT_DRIVE_FILE, ft.colors.GREY_500),
        }
        icon, color = icons.get(file_type, (ft.icons.INSERT_DRIVE_FILE, ft.colors.GREY_400))
        return ft.Icon(icon, size=20, color=color)
    
    # ==================== KEYBOARD SHORTCUTS ====================
    
    def handle_keyboard(self, e: ft.KeyboardEvent):
        """Handle keyboard shortcuts"""
        # Keyboard shortcuts
        if e.key == "Delete":
            if self.selected_files:
                if len(self.selected_files) == 1:
                    self.delete_single_file()
                else:
                    self.start_delete_multiple()
        
        elif e.ctrl and e.key == "a":
            # Ctrl+A - Обрати все
            if not self.selection_mode:
                self.activate_selection_mode()
            self.select_all_files()
        
        elif e.ctrl and e.key == "c":
            self.copy_selected()
        
        elif e.ctrl and e.key == "x":
            self.cut_selected()
        
        elif e.ctrl and e.key == "v":
            self.paste_files()
        
        elif e.key == "Escape":
            # ESC - Вийти з режиму виділення
            if self.selection_mode:
                self.deactivate_selection_mode()
    
    # ==================== INFO PANEL ====================
    
    def show_info_panel_method(self, e=None):
        """Show info panel for selected file using BottomSheet"""
        if len(self.selected_files) != 1:
            return
        
        file_path = list(self.selected_files)[0]
        file_data = next((f for f in self.files_data if f['path'] == file_path), None)
        
        if not file_data:
            return
        
        theme = self.get_theme()
        
        # Get full file info
        name = file_data['name']
        size = self.format_size(file_data['size']) if not file_data['is_dir'] else self.t("fm_folder_type")
        date = file_data.get('full_date', self.t("fm_unknown"))
        path = file_data['path']
        file_type = file_data['type']
        
        # Create BottomSheet content
        info_content = ft.Container(
            content=ft.Column([
                # Header
                ft.Row([
                    ft.Text(self.t("fm_info_title"), size=18, weight=ft.FontWeight.BOLD, color=theme['text']),
                    ft.IconButton(
                        icon=ft.icons.CLOSE,
                        icon_size=20,
                        icon_color=theme['text_secondary'],
                        on_click=lambda e: self.close_info_bottom_sheet(),
                    ),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                
                ft.Divider(height=1, color=theme['divider']),
                
                # File info rows
                ft.Row([
                    self.get_file_icon(file_type),
                    ft.Text(name, size=16, color=theme['text'], weight=ft.FontWeight.W_500, expand=True),
                ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                
                ft.Container(height=8),
                
                # Info details
                self._create_info_row(self.t("fm_col_type"), self._get_file_type_label(file_type, file_data['is_dir']), theme),
                self._create_info_row(self.t("fm_col_size"), size, theme),
                self._create_info_row(self.t("fm_col_date"), date, theme),
                
                ft.Container(height=4),
                
                # Path in scrollable container
                ft.Column([
                    ft.Text(self.t("fm_path") + ":", size=12, color=theme['text_secondary'], weight=ft.FontWeight.W_500),
                    ft.Container(
                        content=ft.Text(path, size=11, color=theme['text_muted'], selectable=True),
                        padding=ft.padding.all(8),
                        bgcolor=theme['hover'],
                        border_radius=4,
                    ),
                ], spacing=4),
            ], spacing=8, tight=True),
            padding=ft.padding.all(20),
        )
        
        # Create or update BottomSheet
        self.info_bottom_sheet = ft.BottomSheet(
            content=info_content,
            open=True,
            bgcolor=theme['card'],
            enable_drag=True,
            show_drag_handle=True,
            use_safe_area=True,
        )
        
        # Add to page overlay
        self.page.overlay.append(self.info_bottom_sheet)
        self.page.update()
    
    def _create_info_row(self, label, value, theme):
        """Create info row for BottomSheet"""
        return ft.Row([
            ft.Text(label + ":", size=12, color=theme['text_secondary'], weight=ft.FontWeight.W_500, width=100),
            ft.Text(value, size=12, color=theme['text'], expand=True),
        ], spacing=12)
    
    def _get_file_type_label(self, file_type, is_dir):
        """Get human-readable file type label"""
        if is_dir:
            return self.t("fm_folder_type")
        
        type_labels = {
            'image': self.t("fm_type_image"),
            'video': self.t("fm_type_video"),
            'audio': self.t("fm_type_audio"),
            'archive': self.t("fm_type_archive"),
            'document': self.t("fm_type_document"),
            'unknown': self.t("fm_type_unknown"),
        }
        return type_labels.get(file_type, file_type.capitalize())
    
    def close_info_bottom_sheet(self):
        """Close info BottomSheet"""
        if self.info_bottom_sheet:
            self.info_bottom_sheet.open = False
            self.page.update()
            # Remove from overlay after animation
            if self.info_bottom_sheet in self.page.overlay:
                self.page.overlay.remove(self.info_bottom_sheet)
            self.info_bottom_sheet = None
    
    # ==================== UI BUILDING ====================
    
    def refresh_files(self):
        """Refresh file list"""
        self.files_data = self.list_files(self.current_path)
        self.update_state()
        self.rebuild_file_list()
        self.update_breadcrumbs()
        self.update_storage_bar()
        self.update_status_bar()
    
    def rebuild_file_list(self):
        """Rebuild file list UI"""
        if not self.files_container:
            return

        theme = self.get_theme()
        rows = []

        # Заголовок таблиці
        header = ft.Container(
            content=ft.Row([
                ft.Container(width=24),  # місце під іконку
                ft.Text(self.t("fm_col_name"), size=12, color=theme['text_secondary'],
                        weight=ft.FontWeight.BOLD, expand=True),
                ft.Text(self.t("fm_col_size"), size=12, color=theme['text_secondary'],
                        weight=ft.FontWeight.BOLD, width=80, text_align=ft.TextAlign.RIGHT),
                ft.Text(self.t("fm_col_date"), size=12, color=theme['text_secondary'],
                        weight=ft.FontWeight.BOLD, width=65, text_align=ft.TextAlign.RIGHT),
            ], spacing=8),
            padding=ft.padding.symmetric(horizontal=8, vertical=6),
            bgcolor=ft.colors.with_opacity(0.15, theme['text_secondary']),
        )
        rows.append(header)

        # Нова папка (inline)
        if self.new_folder_active:
            name_field = ft.TextField(
                hint_text=self.t("fm_folder_name_hint"),
                autofocus=True, text_size=13,
                border_color=ft.colors.GREEN,
                on_submit=lambda e: self.confirm_new_folder(e.control.value),
            )
            rows.append(ft.ListTile(
                leading=ft.Icon(ft.icons.CREATE_NEW_FOLDER, size=20, color=ft.colors.GREEN_500),
                title=name_field,
                trailing=ft.Row([
                    ft.IconButton(ft.icons.CHECK_CIRCLE, icon_size=18, icon_color=ft.colors.GREEN_500,
                                  on_click=lambda e: self.confirm_new_folder(name_field.value)),
                    ft.IconButton(ft.icons.CANCEL, icon_size=18,
                                  on_click=lambda e: self.cancel_new_folder()),
                ], tight=True, spacing=0),
            ))

        if not self.files_data:
            rows.append(ft.ListTile(
                title=ft.Text(self.t("fm_empty_folder"), color=theme['text_secondary'])
            ))

        for file_data in self.files_data:
            is_selected = file_data['path'] in self.selected_files
            is_renaming = self.rename_file_data and file_data['path'] == self.rename_file_data['path']

            _fi = self.get_file_icon(file_data['type'])
            icon, color = _fi.name, _fi.color
            size_str = self.format_size(file_data['size']) if not file_data['is_dir'] else "—"

            # Режим перейменування
            if is_renaming:
                name_field = ft.TextField(
                    value=file_data['name'], autofocus=True, text_size=13,
                    border_color=ft.colors.BLUE,
                    on_submit=lambda e: self.confirm_rename(e.control.value),
                )
                rows.append(ft.ListTile(
                    leading=ft.Icon(icon, size=20, color=color),
                    title=name_field,
                    trailing=ft.Row([
                        ft.IconButton(ft.icons.CHECK_CIRCLE, icon_size=18, icon_color=ft.colors.BLUE_500,
                                      on_click=lambda e, nf=name_field: self.confirm_rename(nf.value)),
                        ft.IconButton(ft.icons.CANCEL, icon_size=18,
                                      on_click=lambda e: self.cancel_rename()),
                    ], tight=True, spacing=0),
                    bgcolor=theme['rename_bg'],
                    content_padding=ft.padding.symmetric(horizontal=4),
                ))
                continue

            # Іконка без чекбокса — виділення через заливку selected_tile_color
            leading = ft.Icon(icon, size=20, color=color)

            list_tile = ft.ListTile(
                leading=leading,
                title=ft.Text(file_data['name'], size=13, no_wrap=True,
                              overflow=ft.TextOverflow.ELLIPSIS),
                trailing=ft.Row([
                    ft.Text(size_str, size=12, color=theme['text_secondary'], width=80,
                            text_align=ft.TextAlign.RIGHT),
                    ft.Text(file_data['modified'], size=12, color=theme['text_secondary'],
                            width=65, text_align=ft.TextAlign.RIGHT),
                ], tight=True, spacing=0),
                selected=is_selected,
                selected_color=theme['text'],
                selected_tile_color=theme['selected'],
                content_padding=ft.padding.symmetric(horizontal=4),
                on_click=lambda e, f=file_data: (
                    self.toggle_selection(f) if self.selection_mode
                    else self.open_file_or_folder(f)
                ),
                on_long_press=lambda e, f=file_data: self.toggle_selection_mode(f['path']),
            )
            # GestureDetector додає підтримку ПКМ (on_secondary_tap)
            tile = ft.GestureDetector(
                content=list_tile,
                on_secondary_tap=lambda e, f=file_data: self.toggle_selection_mode(f['path']),
            )
            rows.append(tile)

        self.files_container.controls = rows
        self.page.update()

    def toggle_selection(self, file_data):
        """Toggle file selection"""
        if file_data['path'] in self.selected_files:
            self.selected_files.remove(file_data['path'])
            # Якщо більше немає виділених - вийти з режиму
            if len(self.selected_files) == 0 and self.selection_mode:
                self.deactivate_selection_mode()
                return
        else:
            self.selected_files.add(file_data['path'])
        
        self.update_state()
        self.rebuild_file_list()
        self.update_status_bar()
    
    def activate_selection_mode(self, file_path=None):
        """Activate selection mode and optionally select a file"""
        self.selection_mode = True
        if file_path:
            self.selected_files.add(file_path)
        self.update_state()
        self.rebuild_file_list()
    
    def toggle_selection_mode(self, file_path):
        """Toggle selection for file via right-click"""
        if self.selection_mode and file_path in self.selected_files:
            # Якщо вже виділено - зняти виділення
            self.selected_files.remove(file_path)
            # Якщо більше нічого не виділено - вийти з режиму
            if len(self.selected_files) == 0:
                self.deactivate_selection_mode()
            else:
                self.update_state()
                self.rebuild_file_list()
        else:
            # Інакше - активувати режим виділення і виділити файл
            self.activate_selection_mode(file_path)
    
    def deactivate_selection_mode(self):
        """Deactivate selection mode and clear selections"""
        self.selection_mode = False
        self.selected_files.clear()
        self.update_state()
        self.rebuild_file_list()
    
    def select_all_files(self):
        """Select all files in current directory"""
        for file_data in self.files_data:
            self.selected_files.add(file_data['path'])
        self.update_state()
        self.rebuild_file_list()
    
    def update_breadcrumbs(self):
        """Update breadcrumbs — show segments from the end fitting available width.
        Hidden earlier segments accessible via '...' popup menu."""
        if not self.breadcrumbs_container:
            return

        theme = self.get_theme()
        path_parts = [p for p in self.current_path.split('/') if p]

        # Realistic TextButton width for size=11 font in Flet
        # ~8.5px per char + 16px padding + Flet overhead; minimum 36px
        def seg_w(part):
            return max(36, len(part) * 8.5 + 16)

        SEP_W  = 18   # width of "/" separator text
        HOME_W = 44   # home icon button
        DOTS_W = 44   # "..." popup button

        # Available width for path segments (subtract dialog paddings ~48px + title bar ~48px)
        available = self._dialog_width - HOME_W - 56

        # Fit segments from the END
        # Strategy: greedily add segments from the end while they fit.
        # Always reserve space for "..." unless ALL segments fit.
        # First pass: check if everything fits without dots
        all_w = sum(seg_w(p) + SEP_W for p in path_parts) - SEP_W
        if all_w <= available:
            count = len(path_parts)
        else:
            # Need dots — reserve their space upfront
            budget = available - DOTS_W - SEP_W
            total_w = 0
            count = 0
            for part in reversed(path_parts):
                w = seg_w(part) + SEP_W
                if total_w + w > budget:
                    break
                total_w += w
                count += 1
            count = max(1, count)

        count = min(count, len(path_parts))
        hidden_parts  = path_parts[:len(path_parts) - count]
        visible_parts = path_parts[len(path_parts) - count:]

        # ---- Build controls ----
        controls = []

        # Home button
        controls.append(
            ft.IconButton(
                icon=ft.icons.HOME,
                icon_size=16,
                on_click=lambda e: self.navigate_to("/storage/emulated/0"),
                tooltip=self.t("fm_home"),
                icon_color=theme['accent'],
            )
        )

        # "..." popup menu for hidden segments
        if hidden_parts:
            menu_items = []
            for i, part in enumerate(hidden_parts):
                target = '/' + '/'.join(path_parts[:i + 1])
                menu_items.append(
                    ft.PopupMenuItem(
                        text=part,
                        on_click=lambda e, p=target: self.navigate_to(p),
                    )
                )

            controls.append(
                ft.PopupMenuButton(
                    content=ft.Container(
                        content=ft.Text("...", size=13, color=theme['accent'],
                                        weight=ft.FontWeight.W_600),
                        padding=ft.padding.symmetric(horizontal=6, vertical=2),
                    ),
                    items=menu_items,
                )
            )
            controls.append(ft.Text('/', size=13, color=theme['text_muted']))

        # Visible segments (from hidden_parts onwards)
        start_idx = len(path_parts) - len(visible_parts)
        for i, part in enumerate(visible_parts):
            idx = start_idx + i
            target_path = '/' + '/'.join(path_parts[:idx + 1])
            is_last = (i == len(visible_parts) - 1)

            controls.append(
                ft.TextButton(
                    content=ft.Text(part, size=13,
                                   color=theme['text'] if is_last else theme['text_secondary']),
                    on_click=lambda e, p=target_path: self.navigate_to(p),
                    style=ft.ButtonStyle(
                        padding=ft.padding.symmetric(horizontal=4, vertical=2),
                    ),
                )
            )
            if not is_last:
                controls.append(ft.Text('/', size=12, color=theme['text_muted']))

        self.breadcrumbs_container.content = ft.Row(controls, spacing=2)
        self.page.update()
    
    def update_storage_bar(self):
        """Update storage info with gradient progress bar"""
        if not self.storage_bar or not self.storage_text:
            return
        
        total, used = self.get_storage_info()
        percent = (used / total * 100) if total > 0 else 0
        
        self.storage_text.value = f"{used:.1f} / {total:.1f} GB"
        self.storage_percent.value = f"{percent:.0f}%"
        self.storage_bar.value = percent / 100
        
        # Color depends on usage
        if percent > 90:
            self.storage_bar.color = ft.colors.RED_500
        elif percent > 75:
            self.storage_bar.color = ft.colors.ORANGE_500
        else:
            self.storage_bar.color = ft.colors.BLUE_500
        
        self.page.update()
    
    def update_status_bar(self):
        """Update status bar with file count"""
        if not self.status_text:
            return
        
        count = len(self.files_data)
        selected = len(self.selected_files)
        
        if selected > 0:
            self.status_text.value = self.t("fm_status_multiple", count=selected, total=count)
        else:
            self.status_text.value = self.t("fm_status_single", count=count)
        
        self.page.update()
    
    def create_dialog(self):
        """Create and configure file manager dialog"""
        theme = self.get_theme()
        
        # Breadcrumbs
        self.breadcrumbs_container = ft.Container(
            content=ft.Row([], spacing=2),
            padding=ft.padding.symmetric(horizontal=0, vertical=6),
            border=ft.border.only(bottom=ft.BorderSide(1, theme['divider'])),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        
        # Dynamic action buttons
        self.toolbar_actions = ft.Row([], spacing=4, alignment=ft.MainAxisAlignment.START)
        
        action_toolbar = ft.Container(
            content=self.toolbar_actions,
            padding=ft.padding.symmetric(horizontal=0, vertical=4),
            # Border below toolbar to separate from file list
            border=ft.border.only(bottom=ft.BorderSide(1, theme['divider'])),
            height=44,  # Фіксована висота щоб не стрибав
            clip_behavior=ft.ClipBehavior.HARD_EDGE,  # Обрізати що виходить за межі
        )
        
        _win_w = self.page.window.width  or 900
        _win_h = self.page.window.height or 700
        _dlg_w = _win_w - 40
        _dlg_h = min(650, _win_h - 100)
        _list_h = _dlg_h - 188
        self._dialog_width = _dlg_w

        # Files container
        self.files_container = ft.ListView(height=_list_h, spacing=0)
        
        files_stack = ft.Stack(
            controls=[self.files_container],
            height=_list_h,
        )
        
        # Storage bar with percentage - increased height for better visibility
        self.storage_bar = ft.ProgressBar(value=0, height=8, color=theme['progress_fill'], bgcolor=theme['progress_bg'], border_radius=4)
        self.storage_text = ft.Text("", size=11, color=theme['text_secondary'])
        self.storage_percent = ft.Text("", size=11, color=theme['text_secondary'], weight=ft.FontWeight.W_500)
        
        # Status text
        self.status_text = ft.Text("", size=11, color=theme['text_secondary'])
        
        # Progress indicator
        self.progress_text = ft.Text("", size=13, color=theme['text'], weight=ft.FontWeight.W_500)
        self.progress_percent = ft.Text("", size=11, color=theme['text_secondary'])
        self.progress_bar = ft.ProgressBar(value=0, width=200, color=theme['progress_fill'], bgcolor=theme['progress_bg'], border_radius=2)
        
        self.progress_container = ft.Container(
            content=ft.Column([
                self.progress_text,
                self.progress_percent,
                self.progress_bar,
            ], tight=True, spacing=4),
            padding=12,
            bgcolor=ft.colors.with_opacity(0.95, theme['card']),
            border_radius=8,
            border=ft.border.all(1, theme['toolbar_border']),
            visible=False,
        )
        
        # Bottom info bar
        bottom_bar = ft.Container(
            content=ft.Column([
                ft.Row([
                    self.status_text,
                    ft.Row([
                        self.storage_text,
                        ft.Container(self.storage_bar, width=80, height=6),
                        self.storage_percent,
                    ], spacing=6),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                self.progress_container,
            ], spacing=4, tight=True),
            padding=ft.padding.symmetric(horizontal=0, vertical=3),
            border=ft.border.only(top=ft.BorderSide(1, theme['divider'])),
        )
        
        # Main content
        content = ft.Column([
            self.breadcrumbs_container,
            action_toolbar,
            files_stack,
            bottom_bar,
        ], spacing=0)
        
        # File picker
        self.file_picker = ft.FilePicker(on_result=self.upload_files)
        self.page.overlay.append(self.file_picker)
        
        # Dialog
        self.dialog = ft.AlertDialog(
            modal=False,
            title=ft.Row([
                ft.Icon(ft.icons.FOLDER_OPEN, color=theme['accent'], size=20),
                ft.Text(self.t("fm_title", device_name=self.device_name), size=16, weight=ft.FontWeight.BOLD, expand=True),
                self._close_btn(),
            ], spacing=8),
            content=ft.Container(
                content=content,
                width=_dlg_w,
                height=_dlg_h,
                bgcolor=ft.colors.TRANSPARENT,
                border_radius=0,
                clip_behavior=ft.ClipBehavior.NONE,
            ),
            actions=[],
            actions_padding=ft.padding.all(0),
            inset_padding=ft.padding.symmetric(horizontal=20, vertical=24),
        )
        
        # Keyboard handler
        self.page.on_keyboard_event = self.handle_keyboard
    
    def close_file_manager(self):
        """Close file manager dialog"""
        if self.dialog:
            self.dialog.open = False
            self.page.update()
        
        # Remove keyboard handler
        self.page.on_keyboard_event = None
        
        # Clean up file pickers
        if self.folder_picker and self.folder_picker in self.page.overlay:
            self.page.overlay.remove(self.folder_picker)
        
        # Clean up temp files
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
        self.temp_files.clear()