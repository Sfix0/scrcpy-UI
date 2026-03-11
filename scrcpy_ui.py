"""
scrcpy UI - Advanced GUI for scrcpy
Version: 3.3 - Added Smart Wi-Fi Auto-Discovery (mDNS + ping sweep)
"""

import flet as ft
import subprocess
import threading
import shutil
import os
import time
import atexit
import sys
import json
import random

from localization import (
    SettingsManager, load_help_content, create_managers,
    # UI Constants
    DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT, MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT,
    FPS_MIN, FPS_MAX, FPS_DEFAULT, FPS_DIVISIONS,
    # ADB Helper Functions
    get_connected_devices, get_device_battery,
    get_battery_icon_and_color, is_device_charging, get_device_info,
    connect_wifi_device, get_default_record_path, create_shortcut, kill_adb_server,
    # Utility Functions
    check_scrcpy_clipboard_support, calculate_max_size,
    # Font utility
    find_custom_font, get_local_network_prefix,
    # WiFi Discovery
    WifiDiscovery,
    # Tool paths
    ADB, SCRCPY,
)

from header import HeaderAnimation, get_time_of_day, get_sky_colors

# Import FileManager module
from file_manager import FileManager

# Import dialogs module
import dialogs

# Register ADB cleanup at exit — only in the main process, NOT in the debug panel subprocess.
# When launched as "--flet-panel", killing adb would drop the active WiFi connection.
if "--flet-panel" not in sys.argv:
    atexit.register(kill_adb_server)


# ==================== MAIN APPLICATION ====================

def main(page: ft.Page):
    # ── mDNS discovery: starts immediately before anything else ──
    _wifi_discovery = WifiDiscovery()
    _wifi_discovery.start()

    if not os.path.exists(SCRCPY) and not shutil.which("scrcpy") or \
       not os.path.exists(ADB) and not shutil.which("adb"):
        page.title = "Missing Dependencies"
        page.window.width = 600
        page.window.height = 400
        page.window.resizable = False
        page.vertical_alignment = ft.MainAxisAlignment.CENTER
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        
        page.clean()
        
        page.add(
            ft.Column(
                [
                    ft.Icon(ft.icons.GPP_BAD, size=64, color=ft.colors.RED),
                    ft.Text("Critical Error: Dependency missing", size=20, weight=ft.FontWeight.BOLD),
                    ft.Text("scrcpy or adb was not found in your system PATH.\nPlease install them to use this application.", 
                           text_align=ft.TextAlign.CENTER, size=16),
                    ft.Container(height=20),
                    ft.ElevatedButton(
                        "Download scrcpy (GitHub)", 
                        icon=ft.icons.OPEN_IN_BROWSER, 
                        on_click=lambda _: page.launch_url("https://github.com/Genymobile/scrcpy")
                    ),
                    ft.Container(height=10),
                    ft.TextButton("Exit", on_click=lambda _: page.window.close())
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
        page.update()
        return

    custom_font = find_custom_font()
    if custom_font:
        page.fonts = {"CustomFont": custom_font}
        page.theme = ft.Theme(font_family="CustomFont")
    else:
        page.theme = ft.Theme()
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    # Create managers using factory function
    settings, lang = create_managers()
    if settings.get("debug_panel_scale") is None:
        settings.set("debug_panel_scale", 1.0)

    scrollbar_style = ft.ScrollbarTheme(
        thickness=6, 
        radius=10,
        main_axis_margin=3,
        cross_axis_margin=3,
        thumb_color={
            ft.ControlState.HOVERED: ft.colors.with_opacity(0.2, ft.colors.BLUE_200),
            ft.ControlState.DEFAULT: ft.colors.with_opacity(0.2, ft.colors.GREY_500),
        },
    )

    if custom_font:
        page.fonts = {"CustomFont": custom_font}
        page.theme = ft.Theme(font_family="CustomFont", scrollbar_theme=scrollbar_style)
    else:
        page.theme = ft.Theme(scrollbar_theme=scrollbar_style)
    # Load saved dimensions
    saved_width = settings.get("window_width", DEFAULT_WINDOW_WIDTH)
    saved_height = settings.get("window_height", DEFAULT_WINDOW_HEIGHT)
    saved_left = settings.get("window_left")
    saved_top = settings.get("window_top")

    page.title = lang.t("app_title")
    page.theme_mode = ft.ThemeMode.DARK if settings.get("theme") == "dark" else ft.ThemeMode.LIGHT
    IS_LIGHT = page.theme_mode == ft.ThemeMode.LIGHT
    page.bgcolor = "#E0E0E0" if IS_LIGHT else None
    _cg = None if IS_LIGHT else ft.LinearGradient(begin=ft.alignment.top_left, end=ft.alignment.bottom_right, colors=[ft.colors.with_opacity(0.05, ft.colors.WHITE), ft.colors.with_opacity(0.01, ft.colors.WHITE)])
    _cb = ft.colors.WHITE if IS_LIGHT else None
    _cbr = ft.border.all(1, ft.colors.with_opacity(0.15, ft.colors.BLACK)) if IS_LIGHT else ft.border.all(1, ft.colors.with_opacity(0.1, ft.colors.WHITE))
    page.window.resizable = True
    page.window.width = saved_width
    page.window.height = saved_height
    page.window.min_width = MIN_WINDOW_WIDTH
    page.window.min_height = MIN_WINDOW_HEIGHT

    if saved_left is not None:
        page.window.left = saved_left
    if saved_top is not None:
        page.window.top = saved_top

    page.padding = 16
    page.scroll = ft.ScrollMode.ADAPTIVE
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH

    # Animation state
    animation_running = [True]

    # UI elements
    debug_control_cb = ft.Checkbox(
        label=lang.t("debug_control_panel"),
        value=False
    )

    debug_overlay = None
    current_scrcpy_process = None
    battery_animation_running = [False]
    current_device_resolution = [None]  # Store current device resolution
    
    # Phone orientation state
    horizontal_rotation = [False]

    def track_window_position():
        """Track and save window position"""
        try:
            if page.window.left == -32000 and page.window.top == -32000:
                return

            settings_file = os.path.join("data", "settings.json")

            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    try:
                        current_settings = json.load(f)
                    except Exception as ex:
                        # Silenced: print(f"Error loading settings: {ex}")
                        current_settings = {}
            else:
                current_settings = {}

            current_settings["window_width"] = int(page.window.width) if page.window.width else DEFAULT_WINDOW_WIDTH
            current_settings["window_height"] = int(page.window.height) if page.window.height else DEFAULT_WINDOW_HEIGHT

            if page.window.left is not None and page.window.left > -1000:
                current_settings["window_left"] = int(page.window.left)
            if page.window.top is not None and page.window.top > -1000:
                current_settings["window_top"] = int(page.window.top)

            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(current_settings, f, indent=2, ensure_ascii=False)

        except Exception as ex:
            pass  # Silenced: print(f"Error saving window position: {ex}")
    
    def save_window_config():
        """Saves window settings only once via SettingsManager"""
        if page.window.left is not None and page.window.left > -1000:
            settings.save_window_size(
                int(page.window.width),
                int(page.window.height),
                int(page.window.left),
                int(page.window.top)
            )

    def on_window_event(e):
        if e.data == "close":
            #We save the dimensions before leaving.
            save_window_config()
            
            animation_running[0] = False
            
            nonlocal debug_overlay
            if debug_overlay:
                debug_overlay.close()
                debug_overlay = None

            nonlocal current_scrcpy_process
            if current_scrcpy_process and current_scrcpy_process.poll() is None:
                try:
                    current_scrcpy_process.terminate()
                    current_scrcpy_process.wait(timeout=5)
                except Exception:
                    try:
                        current_scrcpy_process.kill()
                    except Exception as ex:
                        pass  # Silenced: print(f"Error killing scrcpy process: {ex}")
                current_scrcpy_process = None

            # ADB cleanup if enabled
            if settings.get("kill_adb_on_exit", True):
                kill_adb_server()
            _wifi_discovery.stop()

    page.window.on_event = on_window_event

    def apply_popup_theme():
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        popup_color = ft.colors.GREY_900 if is_dark else ft.colors.WHITE
        base = page.theme or ft.Theme()
        base.popup_menu_theme = ft.PopupMenuTheme(color=popup_color)
        page.theme = base

    def toggle_theme(e):
        new_theme = "light" if page.theme_mode == ft.ThemeMode.DARK else "dark"
        settings.set("theme", new_theme)
        save_window_config()
        animation_running[0] = False
        battery_animation_running[0] = False
        time.sleep(0.1)
        page.clean()
        main(page)

    theme_btn = ft.IconButton(
        icon=ft.icons.NIGHTLIGHT_OUTLINED if settings.get("theme") == "dark" else ft.icons.WB_SUNNY_OUTLINED,
        on_click=toggle_theme, tooltip="Toggle theme", icon_size=20
    )
    apply_popup_theme()

    def toggle_language(e):
        save_window_config()

        available_langs = lang.available_languages()
        current_idx = available_langs.index(lang.current_lang) if lang.current_lang in available_langs else 0
        next_idx = (current_idx + 1) % len(available_langs)
        new_lang = available_langs[next_idx]
        lang.set_language(new_lang)
        settings.set("language", new_lang)
        # Stop background threads before reinitializing the page
        animation_running[0] = False
        battery_animation_running[0] = False
        time.sleep(0.1)
        page.clean()
        main(page)

    lang_btn = ft.TextButton(text=lang.get_language_name(), on_click=toggle_language, tooltip="Change language")

    def show_settings_dialog(_):
        dialogs.show_settings_dialog(page, lang, settings)

    settings_btn = ft.IconButton(icon=ft.icons.SETTINGS, on_click=show_settings_dialog, tooltip=lang.t("settings"), icon_size=20)

    def show_file_manager(_):
        """Show file manager dialog for connected device"""
        serial = device_dropdown.value
        if not serial:
            page.snack_bar = ft.SnackBar(ft.Text("Please select a device first!"))
            page.snack_bar.open = True
            page.update()
            return

        info = get_device_info(serial)
        device_name = info.get("model", "Device")

        # Create file manager instance with language support
        file_manager = FileManager(page, serial, device_name, lang)

        # Create file manager dialog
        file_manager.create_dialog()

        # First, mount the dialog
        page.overlay.append(file_manager.dialog)
        file_manager.dialog.open = True
        page.update()

        # Load files only after mounting
        file_manager.refresh_files()

    def show_help_dialog(_):
        dialogs.show_help_dialog(page, lang, load_help_content)
        
    def show_shortcuts_dialog(_):
        dialogs.show_shortcuts_dialog(page, lang)

    def toggle_phone_orientation(e):
        """Toggle phone orientation between vertical and horizontal"""
        horizontal_rotation[0] = not horizontal_rotation[0]
        
        # Animate rotation
        new_angle = 90 if horizontal_rotation[0] else 0
        phone_orientation_btn.rotate = new_angle * 3.14159 / 180  # Convert degrees to radians
        
        page.update()

    # Phone orientation button with rotation animation
    phone_orientation_btn = ft.IconButton(
        icon=ft.icons.SMARTPHONE,
        icon_size=18,
        on_click=toggle_phone_orientation,
        tooltip=lang.t("toggle_orientation"),
        rotate=0,
        animate_rotation=ft.Animation(500, ft.AnimationCurve.EASE_IN_OUT)
    )

    battery_icon = ft.Icon(ft.icons.BATTERY_UNKNOWN, size=24, color=ft.colors.GREY)
    device_dropdown = ft.Dropdown(label=lang.t("device"), width=200)
    file_manager_btn = ft.IconButton(icon=ft.icons.FOLDER_OPEN, icon_size=24, tooltip=lang.t("file_manager"), on_click=show_file_manager, visible=False)
    device_row = ft.Row(
        [phone_orientation_btn, device_dropdown, battery_icon, file_manager_btn],
        spacing=3,
        wrap=True
    )

    def on_wifi_ip_focus(e):
        """Automatically inserts network prefix if field is empty"""
        if not wifi_ip.value:
            prefix = get_local_network_prefix()
            if prefix:
                wifi_ip.value = prefix
                wifi_ip.update()

    # ==================== END AUTO WIFI DISCOVERY ====================

    # Generate a hint based on a real network (for example: "192.168.31.x:5555")
    _net_prefix = get_local_network_prefix()
    _hint_text = f"{_net_prefix}x:5555" if _net_prefix else lang.t("wifi_placeholder")

    wifi_ip = ft.TextField(
        label=lang.t("wifi_ip"), 
        hint_text=_hint_text, 
        width=225,
        on_focus=on_wifi_ip_focus # Adding a focus event
    )
    status_text = ft.Text("", size=12)
    # Store reference to resolution options for updates
    resolution_dropdown = None
    resolution_row = None

    # Placeholder references for on_resolution_change
    custom_percent_field = None
    custom_percent_slider = None
    custom_percent_label = None
    max_fps_slider = None
    fps_label = None

    def on_resolution_change(e):
        """Handle resolution dropdown changes"""
        if resolution_dropdown is None:
            return
        is_native = resolution_dropdown.value == "native"
        is_custom = resolution_dropdown.value == "custom"
        custom_percent_field.visible = is_custom
        custom_percent_slider.visible = is_custom
        custom_percent_label.visible = is_custom
        max_fps_slider.disabled = is_native
        if is_native:
            fps_label.value = lang.t("fps_unlimited")
        else:
            fps_label.value = f"FPS: {int(max_fps_slider.value)}"
        settings.set("resolution", resolution_dropdown.value)
        update_fps_colors()
        page.update()

    def update_resolution_options(resolution_str=None):
        """Update resolution dropdown with actual dimensions based on device resolution"""
        nonlocal resolution_dropdown, resolution_row

        # Get device resolution (use parameter or stored value)
        if resolution_str is None:
            resolution_str = current_device_resolution[0]

        # Parse resolution string to get actual dimensions
        native_w, native_h = 0, 0
        if resolution_str and "x" in resolution_str:
            try:
                parts = resolution_str.split("x")
                if len(parts) == 2:
                    native_w = int(parts[0].strip())
                    native_h = int(parts[1].strip())
            except (ValueError, IndexError):
                pass

        # Generate options with actual resolutions
        def calc_res(percent):
            if native_w and native_h:
                w = int(native_w * percent / 100)
                h = int(native_h * percent / 100)
                # Keep aspect ratio, show the larger dimension first
                if native_w > native_h:
                    return f"{percent}% ({w}x{h})"
                else:
                    return f"{percent}% ({h}x{w})"
            return f"{percent}%"

        # Build options list
        options_list = [
            ft.dropdown.Option(key="native", text=lang.t("native")),
            ft.dropdown.Option(key="100%", text=lang.t("resolution_100")),
            ft.dropdown.Option(key="80%", text=calc_res(80)),
            ft.dropdown.Option(key="60%", text=calc_res(60)),
            ft.dropdown.Option(key="custom", text=lang.t("custom")),
        ]

        # Create or update dropdown
        current_value = resolution_dropdown.value if resolution_dropdown else settings.get("resolution", "100%")

        if resolution_dropdown is None:
            resolution_dropdown = ft.Dropdown(
                label=lang.t("resolution_percent"),
                options=options_list,
                value=current_value,
                width=280,
                on_change=on_resolution_change,

            )
            resolution_row = ft.Row([ft.Icon(ft.icons.ASPECT_RATIO, size=18), resolution_dropdown], spacing=8)
        else:
            resolution_dropdown.options = options_list
            resolution_dropdown.value = current_value

        # Update resolution row in UI
        if resolution_row:
            resolution_row.controls[1] = resolution_dropdown

        # Update slider state based on current resolution (only if all elements exist)
        if custom_percent_field and custom_percent_slider and max_fps_slider and fps_label:
            on_resolution_change(None)

        # Trigger UI update
        page.update()

    # Initialize resolution dropdown
    update_resolution_options("1920x1080")  # Default placeholder

    # Custom percentage slider (for resolution)
    custom_percent_label = ft.Text("50%", size=13, color=ft.colors.BLUE_GREY_400, visible=False, width=46, no_wrap=True)

    def on_custom_percent_change(e):
        val = int(custom_percent_slider.value)
        custom_percent_label.value = f"{val}%"
        page.update()

    custom_percent_slider = ft.Slider(
        min=15, max=100, value=50, divisions=17,
        label="{value}%",
        height=30,
        width=200,
        active_color=ft.colors.BLUE_GREY_400,
        inactive_color=ft.colors.with_opacity(0.3, ft.colors.BLUE_GREY_400),
        visible=False,
        on_change=on_custom_percent_change,
    )

    custom_percent_field = ft.Row(
        [custom_percent_label, custom_percent_slider],
        visible=False,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=4,
    )
    
    def update_fps_colors():
        """Updates FPS slider colors based on theme"""
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        active_color = ft.colors.ORANGE_400 if is_dark else ft.colors.TEAL_700
        inactive_color = ft.colors.with_opacity(0.3, active_color)
        
        max_fps_slider.active_color = active_color
        max_fps_slider.inactive_color = inactive_color
        fps_label.color = active_color
        page.update()

    max_fps_slider = ft.Slider(
    min=FPS_MIN, max=FPS_MAX, value=settings.get("max_fps", FPS_DEFAULT), divisions=FPS_DIVISIONS,
    label="{value}", height=30,
    active_color=ft.colors.ORANGE_400,
    inactive_color=ft.colors.with_opacity(0.3, ft.colors.ORANGE_400)
    )

    # Set initial FPS slider state based on saved resolution
    saved_resolution = settings.get("resolution", "100%")
    is_native_initial = saved_resolution == "native"
    max_fps_slider.disabled = is_native_initial
    fps_label = ft.Text(
        lang.t("fps_unlimited") if is_native_initial else f"FPS: {int(settings.get('max_fps', FPS_DEFAULT))}",
        size=13, color=ft.colors.ORANGE_400
    )

    # Apply initial colors based on theme
    update_fps_colors()

    def on_fps_change(_):
        fps_label.value = f"FPS: {int(max_fps_slider.value)}"
        page.update()

    max_fps_slider.on_change = on_fps_change

    # Bitrate dropdown options - use constants from localization
    bitrate_options = [
        ft.dropdown.Option(key="2M", text=lang.t("bitrate_low")),
        ft.dropdown.Option(key="8M", text=lang.t("bitrate_standard")),
        ft.dropdown.Option(key="15M", text=lang.t("bitrate_high")),
        ft.dropdown.Option(key="30M", text=lang.t("bitrate_max")),
    ]
    bitrate_dropdown = ft.Dropdown(
        label=lang.t("bitrate"),
        options=bitrate_options,
        value=settings.get("bit_rate", "8M"),
        width=280,
    )

    def on_bitrate_change(_):
        settings.set("bit_rate", bitrate_dropdown.value)

    bitrate_dropdown.on_change = on_bitrate_change
    keyboard_options = [
        ft.dropdown.Option(key="sdk", text=lang.t("keyboard_sdk")),
        ft.dropdown.Option(key="uhid", text=lang.t("keyboard_uhid")),
        ft.dropdown.Option(key="text", text=lang.t("keyboard_text")),
    ]
    keyboard_dropdown = ft.Dropdown(label=lang.t("keyboard_input"), options=keyboard_options, value=settings.get("keyboard_mode", "uhid"), width=252)

    clipboard_cb = ft.Checkbox(
        label=lang.t("clipboard_enable"),
        value=settings.get("clipboard_sync", False),
        on_change=lambda e: settings.set("clipboard_sync", clipboard_cb.value)
    )

    clipboard_desc = ft.Text(
        lang.t("clipboard_desc"),
        size=11,
        color=ft.colors.GREY_700,
        italic=True
    )

    keyboard_and_clipboard_card = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.icons.KEYBOARD, size=18),
                ft.Text(lang.t("keyboard_and_clipboard"), size=16, weight=ft.FontWeight.BOLD)
            ]),
            ft.Divider(height=1),

            keyboard_dropdown,

            ft.Divider(height=8, color=ft.colors.TRANSPARENT),

            ft.Row([
                ft.Icon(ft.icons.CONTENT_PASTE, size=16),
                ft.Text(lang.t("clipboard"), size=13, weight=ft.FontWeight.W_500)
            ]),
            clipboard_cb,
            clipboard_desc
        ], spacing=8),
        padding=12,
        border_radius=12,
        bgcolor=_cb, gradient=_cg, border=_cbr,
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=5,
            color=ft.colors.with_opacity(0.3, ft.colors.BLACK),
            offset=ft.Offset(0, 4)
        ),
        opacity=0,
        scale=ft.Scale(0.96),
        animate_opacity=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
    )

    def on_keyboard_change(_):
        settings.set("keyboard_mode", keyboard_dropdown.value)
    keyboard_dropdown.on_change = on_keyboard_change

    # Toggle state storage
    _hevc_on      = [settings.get("use_hevc", False)]
    _fs_on        = [settings.get("fullscreen", False)]
    _awake_on     = [settings.get("stay_awake", True)]
    _screen_off_on= [settings.get("turn_screen_off", False)]

    _TOGGLE_ON  = ft.colors.BLUE_400
    _TOGGLE_OFF = ft.colors.GREY_600

    def _make_toggle_btn(state_ref, icon_on, icon_off, tooltip_key):
        def _toggle(e):
            state_ref[0] = not state_ref[0]
            btn.icon = icon_on if state_ref[0] else icon_off
            btn.icon_color = _TOGGLE_ON if state_ref[0] else _TOGGLE_OFF
            btn.update()
        btn = ft.IconButton(
            icon=icon_on if state_ref[0] else icon_off,
            icon_color=_TOGGLE_ON if state_ref[0] else _TOGGLE_OFF,
            tooltip=lang.t(tooltip_key),
            on_click=_toggle,
            icon_size=26,
        )
        return btn

    # H.265 — text badge with the same color
    def _toggle_hevc(e):
        _hevc_on[0] = not _hevc_on[0]
        use_hevc_cb.bgcolor = ft.colors.with_opacity(0.15, _TOGGLE_ON) if _hevc_on[0] else ft.colors.TRANSPARENT
        use_hevc_cb.border  = ft.border.all(1.5, _TOGGLE_ON if _hevc_on[0] else _TOGGLE_OFF)
        _hevc_label.color   = _TOGGLE_ON if _hevc_on[0] else _TOGGLE_OFF
        use_hevc_cb.update()

    _hevc_label = ft.Text(
        "H.265", size=11, weight=ft.FontWeight.BOLD,
        color=_TOGGLE_ON if _hevc_on[0] else _TOGGLE_OFF,
    )
    use_hevc_cb = ft.Container(
        content=_hevc_label,
        bgcolor=ft.colors.with_opacity(0.15, _TOGGLE_ON) if _hevc_on[0] else ft.colors.TRANSPARENT,
        border=ft.border.all(1.5, _TOGGLE_ON if _hevc_on[0] else _TOGGLE_OFF),
        border_radius=6,
        padding=ft.padding.symmetric(horizontal=8, vertical=5),
        tooltip=lang.t("tooltip_hevc"),
        on_click=_toggle_hevc,
        animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
    )

    fullscreen_cb      = _make_toggle_btn(_fs_on,         ft.icons.FULLSCREEN,    ft.icons.FULLSCREEN_EXIT, "tooltip_fullscreen")
    stay_awake_cb      = _make_toggle_btn(_awake_on,      ft.icons.LIGHT_MODE,    ft.icons.BEDTIME,         "tooltip_stay_awake")
    turn_screen_off_cb = _make_toggle_btn(_screen_off_on, ft.icons.PHONE_ANDROID, ft.icons.MOBILE_OFF,      "tooltip_turn_screen_off")



    record_cb = ft.Checkbox(label=lang.t("enable_recording"), value=settings.get("record_enabled", False), fill_color=ft.colors.RED_600)
    record_path = ft.TextField(label=lang.t("record_path"), read_only=True, visible=False, width=400)

    def toggle_record_ui(_):
        record_path.visible = record_cb.value
        if record_cb.value and not record_path.value:
            record_path.value = get_default_record_path()
        settings.set("record_enabled", record_cb.value)
        page.update()

    record_cb.on_change = toggle_record_ui

    def animate_battery_charging():
        battery_animation_running[0] = True
        while battery_animation_running[0]:
            try:
                battery_icon.opacity = 0.3 if battery_icon.opacity == 1.0 else 1.0
                page.update()
                time.sleep(1.5)
            except Exception as ex:
                pass  # Silenced: print(f"Battery animation error: {ex}")
                break
        battery_icon.opacity = 1.0

    def update_battery_icon():
        if not device_dropdown.value:
            battery_icon.name = ft.icons.BATTERY_UNKNOWN
            battery_icon.color = ft.colors.GREY
            battery_animation_running[0] = False
            page.update()
            return

        serial = device_dropdown.value
        battery_level = get_device_battery(serial)
        is_charging = is_device_charging(serial)

        icon, color = get_battery_icon_and_color(battery_level, is_charging)
        battery_icon.name = icon
        battery_icon.color = color

        if is_charging and not battery_animation_running[0]:
            threading.Thread(target=animate_battery_charging, daemon=True).start()
        elif not is_charging:
            battery_animation_running[0] = False
            battery_icon.opacity = 1.0
        page.update()

    def refresh_devices(e=None):
        """Refresh device list; animates button on manual call (e is not None)"""
        if e is not None and hasattr(refresh_btn, 'rotate'):
            def animate_refresh():
                try:
                    refresh_btn.rotate = 0
                    page.update()
                    time.sleep(0.05)
                    refresh_btn.rotate = 6.28
                    page.update()
                    time.sleep(0.5)
                    refresh_btn.rotate = 0
                    page.update()
                except Exception:
                    pass
            threading.Thread(target=animate_refresh, daemon=True).start()

        status_text.value = lang.t("status_scanning")
        page.update()

        devices = get_connected_devices()
        options = []

        for d in devices:
            info = get_device_info(d)
            display_name = info["model"]
            if info["battery"] is not None:
                display_name = f"{display_name} {info['battery']}%"
            options.append(ft.dropdown.Option(key=d, text=display_name))

        if devices:
            device_dropdown.value = devices[0]
            device_dropdown.options = options
            info = get_device_info(devices[0])
            status_text.value = f"{info['model']} Android {info['android']} {info['resolution']}"
            file_manager_btn.visible = True
            update_battery_icon()
            current_device_resolution[0] = info.get("resolution", "1920x1080")
            update_resolution_options(current_device_resolution[0])
        else:
            device_dropdown.value = None
            device_dropdown.options = []
            status_text.value = lang.t("status_no_devices")
            file_manager_btn.visible = False
            battery_icon.name = ft.icons.BATTERY_UNKNOWN
            battery_icon.color = ft.colors.GREY
            current_device_resolution[0] = "1920x1080"
            update_resolution_options("1920x1080")

        page.update()

    def on_device_select(_):
        if device_dropdown.value:
            info = get_device_info(device_dropdown.value)
            status_text.value = f"{info['model']} Android {info['android']} {info['resolution']}"
            file_manager_btn.visible = True
            update_battery_icon()
            # Update resolution options with device resolution
            current_device_resolution[0] = info.get("resolution", "1920x1080")
            update_resolution_options(current_device_resolution[0])
            page.update()

    device_dropdown.on_change = on_device_select

    def auto_refresh():
        def animate_device_card_pulse():
            """Cyan breathing effect for device_card during auto-refresh"""
            try:
                if IS_LIGHT:
                    # Light theme: animate bgcolor (shadow hidden behind white card)
                    device_card.bgcolor = ft.colors.with_opacity(0.15, ft.colors.CYAN)
                    device_card.border = ft.border.all(1, ft.colors.with_opacity(0.5, ft.colors.CYAN))
                else:
                    # Dark theme: animate shadow glow
                    device_card.shadow = ft.BoxShadow(spread_radius=3, blur_radius=12, color=ft.colors.with_opacity(0.55, ft.colors.CYAN), offset=ft.Offset(0, 0))
                device_card.update()

                time.sleep(1)  # Hold at peak

                # Restore
                device_card.bgcolor = _cb
                device_card.border = _cbr
                device_card.shadow = ft.BoxShadow(spread_radius=1, blur_radius=5, color=ft.colors.with_opacity(0.3, ft.colors.BLACK), offset=ft.Offset(0, 4))
                device_card.update()
            except Exception as ex:
                pass  # Silenced: print(f"Device card animation error: {ex}")

        
        def refresh_loop():
            while animation_running[0]:
                time.sleep(5) 
                try:
                    # Skip if window is not visible
                    if not page.window.visible:
                        continue
                    
                    # Animate device card
                    animate_device_card_pulse()
                    
                    # Silent refresh without button animation
                    refresh_devices()
                    
                    if device_dropdown.value:
                        update_battery_icon()
                    track_window_position()
                except Exception as ex:
                    pass  # Silenced: print(f"Auto refresh error: {ex}")
        threading.Thread(target=refresh_loop, daemon=True).start()


    def animate_device_card_found():
        """Green border flash on dropdown when mDNS device is successfully connected"""
        try:
            device_dropdown.border_color = ft.colors.GREEN
            page.update()
            time.sleep(1.5)
            device_dropdown.border_color = None
            page.update()
        except Exception:
            pass

    def launch_scrcpy_and_restore_ui(args, serial, debug_control_mode=False):
        nonlocal current_scrcpy_process

        control_panel = None

        # 1. Hide UI safely
        page.window.visible = False
        page.update()

        try:
            creationflags = 0
            if os.name == 'nt' and settings.get("hide_console", True):
                creationflags = subprocess.CREATE_NO_WINDOW

            # Check if we can use the debug panel
            try:
                from debug_mod import AdvancedControlPanel
                DEBUG_MOD_AVAILABLE = True
            except ImportError:
                DEBUG_MOD_AVAILABLE = False
                AdvancedControlPanel = None

            # 2. Launch Scrcpy
            if debug_control_mode and DEBUG_MOD_AVAILABLE:
                try:
                    mode = "extended" if settings.get("extended_metrics", False) else "standard"
                    args_with_fps = args + ["--print-fps"]
                    
                    # Start Scrcpy (don't use startupinfo with PIPE - it breaks!)
                    current_scrcpy_process = subprocess.Popen(
                        [SCRCPY] + args_with_fps,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        creationflags=creationflags
                    )
                    
                    # NOTE: stdout is drained by _relay_scrcpy_fps_socket in debug_mod.py.
                    # A separate drain thread would compete for the same pipe and steal FPS lines.

                    # Write PID file so debug panel can monitor scrcpy lifetime
                    import tempfile as _tmpmod
                    pid_file = os.path.join(_tmpmod.gettempdir(), f"scrcpy_pid_{serial}.txt")
                    try:
                        with open(pid_file, "w") as pf:
                            pf.write(str(current_scrcpy_process.pid))
                    except Exception:
                        pass

                    # Start Debug Panel
                    control_panel = AdvancedControlPanel(
                        serial=serial,
                        scrcpy_process=current_scrcpy_process,
                        mode=mode
                    )
                    
                    # Start panel in a thread (which spawns the subprocess)
                    threading.Thread(
                        target=control_panel.create_window,
                        daemon=True
                    ).start()

                    # Wait for scrcpy to finish
                    current_scrcpy_process.wait()

                except Exception as e:
                    pass  # Silenced: print(f"Error in debug mode: {e}")
                    # Fallback
                    if current_scrcpy_process:
                        current_scrcpy_process.kill()
                    subprocess.run([SCRCPY] + args, creationflags=creationflags)

            else:
                # Normal mode
                subprocess.run([SCRCPY] + args, creationflags=creationflags)

        except Exception as e:
            pass  # Silenced: print(f"Launch error: {e}")
            
        finally:
            # 3. CRITICAL: Cleanup and Restore UI
            
            # Clean up PID file
            try:
                import tempfile as _tmpmod
                pid_file = os.path.join(_tmpmod.gettempdir(), f"scrcpy_pid_{serial}.txt")
                if os.path.exists(pid_file):
                    os.remove(pid_file)
            except Exception:
                pass

            # Give debug panel time to detect scrcpy exit and close itself
            time.sleep(1.5)

            # Close the control panel explicitly if it's still defined locally
            if control_panel:
                try:
                    control_panel.close()
                except:
                    pass
                control_panel = None

            current_scrcpy_process = None

            # Force UI to reappear on the main thread
            def restore_ui_safe():
                try:
                    page.window.visible = True
                    page.window.minimized = False
                    page.update()
                    # Reset connection button icon
                    connect_btn_content.icon = ft.icons.PLAY_ARROW
                    connect_btn_content.update()
                except Exception as ex:
                    pass  # Silenced: print(f"UI Restore error: {ex}")

            # Flet thread-safe call
            try:
                if hasattr(page, 'run_thread'):
                    page.run_thread(restore_ui_safe)
                else:
                    restore_ui_safe()
            except Exception:
                restore_ui_safe()

    def on_connect_click(e):
        serial = device_dropdown.value
        ip = wifi_ip.value.strip()
        debug_control_mode = debug_control_cb.value

        # Helper function for changing the icon inside a complex button
        def update_btn_icon(icon_name):
            connect_btn_icon_only.content.name = icon_name
            connect_btn_row.controls[0].name = icon_name
            connect_btn_content.update()

        if not serial and not ip:
            status_text.value = f"❌ {lang.t('status_select_device')}"
            page.update()
            return

        if ip:
            # Show connection animation on button
            update_btn_icon(ft.icons.HOURGLASS_EMPTY)

            connected = False
            for attempt in range(3):
                if connect_wifi_device(ip):
                    connected = True
                    break
                time.sleep(1)

            if not connected:
                status_text.value = f"❌ {lang.t('status_connection_failed')} {ip}"
                update_btn_icon(ft.icons.PLAY_ARROW)
                return

            time.sleep(2)

            devices = get_connected_devices()
            target = None
            ip_base = ip.split(':')[0]
            for d in devices:
                if ip_base in d or ip in d:
                    target = d
                    break

            if not target:
                if ip_base:
                    status_text.value = f"⚠️ Device may need manual pairing. Trying IP: {ip_base}"
                    page.update()
                    target = ip

            if not target:
                status_text.value = f"❌ {lang.t('status_device_not_found')}"
                update_btn_icon(ft.icons.PLAY_ARROW)
                return

            serial = target

        # Apply phone rotation before launching scrcpy
        if horizontal_rotation[0] and serial:
            try:
                _si = None
                _cf = 0
                if os.name == 'nt':
                    _si = subprocess.STARTUPINFO()
                    _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    _si.wShowWindow = subprocess.SW_HIDE
                    _cf = subprocess.CREATE_NO_WINDOW
                cmd = [ADB, "-s", serial, "shell", "settings put system accelerometer_rotation 0 && settings put system user_rotation 1 && wm user-rotation lock 1"]
                subprocess.run(cmd, capture_output=True, text=True, timeout=5,
                               startupinfo=_si, creationflags=_cf)
                time.sleep(0.5)  # Give time for rotation to apply
            except Exception as ex:
                pass

        args = ["--serial", serial]

        # Calculate max-size based on percentage and device resolution
        is_native = resolution_dropdown.value == "native"

        if not is_native:
            max_size_value = None

            if resolution_dropdown.value == "custom":
                # Custom percentage from slider
                try:
                    percent = int(custom_percent_slider.value)
                    if 1 <= percent <= 100:
                        device_info = get_device_info(serial)
                        max_size_value = calculate_max_size(device_info.get("resolution", ""), percent)
                except (ValueError, AttributeError):
                    pass
            elif resolution_dropdown.value in ["100%", "80%", "60%"]:
                # Fixed percentage options
                try:
                    percent = int(resolution_dropdown.value.replace("%", ""))
                    device_info = get_device_info(serial)
                    max_size_value = calculate_max_size(device_info.get("resolution", ""), percent)
                except (ValueError, AttributeError):
                    pass

            if max_size_value:
                args += ["--max-size", max_size_value]

            # Add FPS parameter (controllable)
            args += ["--max-fps", str(int(max_fps_slider.value))]

        # Add bitrate from dropdown
        args += ["--video-bit-rate", bitrate_dropdown.value]

        kb_mode = keyboard_dropdown.value
        if kb_mode == "uhid":
            args += ["--keyboard=uhid"]
        elif kb_mode == "text":
            args += ["--keyboard=sdk", "--prefer-text"]

        if _hevc_on[0]:
            args += ["--video-codec", "h265"]
        if _fs_on[0]:
            args.append("--fullscreen")
        if _awake_on[0]:
            args.append("--stay-awake")
        if _screen_off_on[0]:
            args.append("--turn-screen-off")

        if settings.get("clipboard_sync", False):
            if check_scrcpy_clipboard_support():
                args.append("--clipboard-sync")
            else:
                pass

        if record_cb.value:
            record_file = record_path.value or get_default_record_path()
            args += ["--record", record_file]
            status_text.value = f"✅ {lang.t('status_launching')} {get_device_info(serial)['model']} {lang.t('status_recording')}..."
        else:
            status_text.value = f"✅ {lang.t('status_launching')} {get_device_info(serial)['model']}..."

        update_btn_icon(ft.icons.CHECK_CIRCLE)

        settings.set("max_fps", int(max_fps_slider.value))
        settings.set("bit_rate", bitrate_dropdown.value)
        settings.set("use_hevc", _hevc_on[0])
        settings.set("keyboard_mode", kb_mode)
        settings.set("fullscreen", _fs_on[0])
        settings.set("stay_awake", _awake_on[0])
        settings.set("turn_screen_off", _screen_off_on[0])

        page.update()

        def restore_and_launch():
            time.sleep(0.5)
            connect_btn_icon_only.content.name = ft.icons.PLAY_ARROW
            connect_btn_row.controls[0].name = ft.icons.PLAY_ARROW
            connect_btn_content.update()
            
            launch_scrcpy_and_restore_ui(args, serial, debug_control_mode)
            
        threading.Thread(target=restore_and_launch, daemon=True).start()

    def create_shortcut_click(e):
        if not device_dropdown.value:
            status_text.value = "❌ Select device first!"
            page.update()
            return

        serial = device_dropdown.value
        info = get_device_info(serial)
        model_name = info["model"]
        args = []

        # Calculate max-size based on percentage and device resolution
        is_native = resolution_dropdown.value == "native"

        if not is_native:
            max_size_value = None

            if resolution_dropdown.value == "custom":
                # Custom percentage from slider
                try:
                    percent = int(custom_percent_slider.value)
                    if 1 <= percent <= 100:
                        max_size_value = calculate_max_size(info.get("resolution", ""), percent)
                except (ValueError, AttributeError):
                    pass
            elif resolution_dropdown.value in ["100%", "80%", "60%"]:
                # Fixed percentage options
                try:
                    percent = int(resolution_dropdown.value.replace("%", ""))
                    max_size_value = calculate_max_size(info.get("resolution", ""), percent)
                except (ValueError, AttributeError):
                    pass

            if max_size_value:
                args += ["--max-size", max_size_value]

            # Add FPS parameter (controllable)
            args += ["--max-fps", str(int(max_fps_slider.value))]

        # Add bitrate
        args += ["--video-bit-rate", bitrate_dropdown.value]

        kb_mode = keyboard_dropdown.value
        if kb_mode == "uhid":
            args += ["--keyboard=uhid"]
        elif kb_mode == "text":
            args += ["--keyboard=sdk", "--prefer-text"]

        if _hevc_on[0]:
            args += ["--video-codec", "h265"]
        if _fs_on[0]:
            args.append("--fullscreen")
        if _awake_on[0]:
            args.append("--stay-awake")
        if _screen_off_on[0]:
            args.append("--turn-screen-off")

        if settings.get("clipboard_sync", False):
            if check_scrcpy_clipboard_support():
                args.append("--clipboard-sync")
            else:
                pass

        if record_cb.value:
            record_file = record_path.value or get_default_record_path()
            args += ["--record", record_file]

        bat_path = create_shortcut(serial, args, model_name)
        status_text.value = f"✅ Shortcut created: {os.path.basename(bat_path)}"
        page.update()

    connect_btn_label = ft.Text(lang.t("connect"), color=ft.colors.WHITE, size=12, weight=ft.FontWeight.BOLD, no_wrap=True)
    connect_btn_row = ft.Row([ft.Icon(ft.icons.PLAY_ARROW, color=ft.colors.WHITE, size=20), connect_btn_label], alignment=ft.MainAxisAlignment.CENTER, spacing=6, tight=True, opacity=0, animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN))
    connect_btn_icon_only = ft.Container(content=ft.Icon(ft.icons.PLAY_ARROW, color=ft.colors.WHITE, size=20), alignment=ft.alignment.center, animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN))
    connect_btn_content = ft.Container(
        content=ft.Stack([connect_btn_icon_only, ft.Container(content=connect_btn_row, alignment=ft.alignment.center)]),
        width=44, height=40, border_radius=8, bgcolor=ft.colors.GREY_700,
        animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT), on_click=on_connect_click,
        shadow=ft.BoxShadow(blur_radius=8, color=ft.colors.with_opacity(0.3, ft.colors.GREEN_400), offset=ft.Offset(0, 3)),
    )
    def on_connect_btn_hover(e):
        hovered = e.data == "true"
        connect_btn_content.width = 150 if hovered else 44
        connect_btn_content.bgcolor = ft.colors.GREEN_600 if hovered else ft.colors.GREY_700
        connect_btn_icon_only.opacity = 0 if hovered else 1
        connect_btn_row.opacity = 1 if hovered else 0
        connect_btn_content.update()
    connect_btn_content.on_hover = on_connect_btn_hover
    connect_btn = ft.Container(content=connect_btn_content)

    refresh_btn = ft.IconButton(icon=ft.icons.REFRESH, on_click=refresh_devices, tooltip=lang.t("refresh"), icon_size=24, icon_color=ft.colors.BLUE_600, animate_rotation=ft.Animation(500, ft.AnimationCurve.EASE_IN_OUT))

    ACCENT = ft.colors.CYAN_600
    ACCENT_SHADOW = ft.colors.with_opacity(0.35, ft.colors.CYAN_400)

    def make_hover_btn(icon, label, on_click):
        """Icon only → on hover: expands to show icon + text, smooth 300ms."""
        icon_only = ft.Container(
            content=ft.Icon(icon, color=ft.colors.WHITE, size=18),
            alignment=ft.alignment.center,
            animate_opacity=ft.Animation(200, ft.AnimationCurve.EASE_IN_OUT),
        )
        label_row = ft.Row(
            [ft.Icon(icon, color=ft.colors.WHITE, size=18),
             ft.Text(label, color=ft.colors.WHITE, size=12, weight=ft.FontWeight.BOLD, no_wrap=True)],
            alignment=ft.MainAxisAlignment.CENTER, spacing=6, tight=True,
            opacity=0, animate_opacity=ft.Animation(200, ft.AnimationCurve.EASE_IN_OUT),
        )
        btn = ft.Container(
            content=ft.Stack([icon_only, ft.Container(content=label_row, alignment=ft.alignment.center)]),
            width=40, height=36, border_radius=8, bgcolor=ft.colors.GREY_700,
            animate=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT), on_click=on_click,
            shadow=ft.BoxShadow(blur_radius=8, color=ACCENT_SHADOW, offset=ft.Offset(0, 3)),
            ink=False,
        )
        def on_hover(e, b=btn, il=icon_only, lr=label_row):
            hovered = e.data == "true"
            b.width = 143 if hovered else 40
            b.bgcolor = ACCENT if hovered else ft.colors.GREY_700
            il.opacity = 0 if hovered else 1
            lr.opacity = 1 if hovered else 0
            b.update()
        btn.on_hover = on_hover
        return btn

    help_btn     = make_hover_btn(ft.icons.HELP_OUTLINE, lang.t("help"),        show_help_dialog)
    shortcuts_btn = make_hover_btn(ft.icons.KEYBOARD,    lang.t("shortcuts"),   show_shortcuts_dialog)
    about_btn    = make_hover_btn(ft.icons.INFO_OUTLINE,  lang.t("about_title"), lambda _: dialogs.show_about_dialog(page, lang))

    # Shortcut button — same style, always shows label, притиснута вправо
    sc_icon_only = ft.Container(content=ft.Icon(ft.icons.ADD_TO_HOME_SCREEN, color=ft.colors.WHITE, size=18), alignment=ft.alignment.center, opacity=0, animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN))
    sc_label_row = ft.Row([ft.Icon(ft.icons.ADD_TO_HOME_SCREEN, color=ft.colors.WHITE, size=18), ft.Text(lang.t("create_shortcut"), color=ft.colors.WHITE, size=12, weight=ft.FontWeight.BOLD, no_wrap=True)], alignment=ft.MainAxisAlignment.CENTER, spacing=6, tight=True)
    sc_btn_inner = ft.Container(
        content=ft.Stack([sc_icon_only, ft.Container(content=sc_label_row, alignment=ft.alignment.center)]),
        width=190, height=36, border_radius=8, bgcolor=ft.colors.GREY_700,
        animate=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT), on_click=create_shortcut_click,
        shadow=ft.BoxShadow(blur_radius=8, color=ACCENT_SHADOW, offset=ft.Offset(0, 3)),
        ink=False,
    )
    def on_sc_hover(e):
        hovered = e.data == "true"
        sc_btn_inner.bgcolor = ACCENT if hovered else ft.colors.GREY_700
        sc_btn_inner.update()
    sc_btn_inner.on_hover = on_sc_hover

    bottom_bar = ft.Container(
        content=ft.Row(
            [help_btn, shortcuts_btn, about_btn, ft.Container(expand=True), sc_btn_inner],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.padding.symmetric(horizontal=6, vertical=6),
        border_radius=12,
        bgcolor=_cb, gradient=_cg, border=_cbr,
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=5, color=ft.colors.with_opacity(0.3, ft.colors.BLACK), offset=ft.Offset(0, 4)),
        opacity=0,
        scale=ft.Scale(0.96),
        animate_opacity=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
    )
    shortcut_btn = bottom_bar
    help_btn = bottom_bar
    shortcuts_btn = bottom_bar
    about_btn = bottom_bar

    # ==================== NEW HEADER IMPLEMENTATION ====================
    
    # Callback to change gradient color from module header
    def on_header_gradient_change(colors):
        header_container.gradient.colors = colors
        header_container.update()

    # We get the initial colors
    initial_period = get_time_of_day()
    initial_colors = get_sky_colors(initial_period)

    # Initializing a new animation component
    header_animation = HeaderAnimation(
        width=500,  # Width as in the old constant ANIMATION_STAR_WIDTH
        height=80,
        on_gradient_change=on_header_gradient_change
    )

    header_container = ft.Container(
        content=ft.Stack([
            header_animation,
            
            ft.Container(
                content=ft.Row([
                    ft.Text(lang.t("app_title"), size=22, weight=ft.FontWeight.BOLD, color=ft.colors.WHITE),
                    ft.Row([lang_btn, theme_btn, settings_btn], spacing=5)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=15
            )
        ]),
        border_radius=12,
        gradient=ft.LinearGradient(
            begin=ft.alignment.center_left,
            end=ft.alignment.center_right,
            colors=initial_colors
        ),
        shadow=ft.BoxShadow(
            spread_radius=2, 
            blur_radius=5, 
            color=ft.colors.with_opacity(0.3, ft.colors.BLUE) if page.theme_mode == ft.ThemeMode.DARK else ft.colors.with_opacity(0.15, ft.colors.GREY_400), 
            offset=ft.Offset(0, 4)
        ),
        animate=ft.Animation(2000, ft.AnimationCurve.EASE_IN_OUT),
        opacity=0,
        scale=ft.Scale(0.96),
        animate_opacity=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
    )
    # ===================================================================

    device_card = ft.Container(
        content=ft.Column([
            ft.Row([device_row, refresh_btn], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([wifi_ip, connect_btn], alignment=ft.MainAxisAlignment.START),
            debug_control_cb,
            status_text
        ], spacing=8),
        padding=12, border_radius=12,
        bgcolor=_cb, gradient=_cg, border=_cbr,
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=5, color=ft.colors.with_opacity(0.3, ft.colors.BLACK), offset=ft.Offset(0, 4)),
        animate=ft.Animation(2000, ft.AnimationCurve.EASE_IN_OUT),
        opacity=0,
        scale=ft.Scale(0.96),
        animate_opacity=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
    )

    settings_card = ft.Container(
        content=ft.Column([
            ft.Row([ft.Icon(ft.icons.SETTINGS, size=18), ft.Text(lang.t("settings"), size=16, weight=ft.FontWeight.BOLD)]),
            ft.Divider(height=1),
            ft.Row([resolution_row, custom_percent_field], wrap=True),
            fps_label, max_fps_slider,
            bitrate_dropdown,
            ft.Row(
                [use_hevc_cb, fullscreen_cb, stay_awake_cb, turn_screen_off_cb],
                spacing=4,
                wrap=True,
            )
        ], spacing=8),
        padding=12, border_radius=12,
        bgcolor=_cb, gradient=_cg, border=_cbr,
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=5, color=ft.colors.with_opacity(0.3, ft.colors.BLACK), offset=ft.Offset(0, 4)),
        opacity=0,
        scale=ft.Scale(0.96),
        animate_opacity=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
    )

    recording_card = ft.Container(
        content=ft.Column([
            ft.Row([ft.Icon(ft.icons.FIBER_MANUAL_RECORD, size=18, color=ft.colors.RED_600), ft.Text(lang.t("recording"), size=16, weight=ft.FontWeight.BOLD)]),
            ft.Divider(height=1),
            record_cb, record_path
        ], spacing=8),
        padding=12, border_radius=12,
        bgcolor=_cb, gradient=_cg, border=_cbr,
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=5, color=ft.colors.with_opacity(0.3, ft.colors.BLACK), offset=ft.Offset(0, 4)),
        opacity=0,
        scale=ft.Scale(0.96),
        animate_opacity=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
        animate_scale=ft.Animation(280, ft.AnimationCurve.EASE_OUT),
    )

    page.add(
        header_container,
        ft.Divider(height=20, color=ft.colors.TRANSPARENT),
        device_card,
        ft.Divider(height=10, color=ft.colors.TRANSPARENT),
        settings_card,
        ft.Divider(height=10, color=ft.colors.TRANSPARENT),
        keyboard_and_clipboard_card,
        ft.Divider(height=10, color=ft.colors.TRANSPARENT),
        recording_card,
        ft.Divider(height=10, color=ft.colors.TRANSPARENT),
        shortcut_btn,
    )

    # Start animations after UI is fully rendered
    def start_animations():
        """Start animations after UI is ready — cascade fade-in"""
        time.sleep(0.15)  # Allow Flet to finish UI rendering

        cascade_elements = [
            header_container,
            device_card,
            settings_card,
            keyboard_and_clipboard_card,
            recording_card,
            shortcut_btn,
        ]

        for element in cascade_elements:
            time.sleep(0.06)  # 60ms delay between each element
            element.opacity = 1
            element.scale = ft.Scale(1.0)
            element.update()

        refresh_devices()
        auto_refresh()

        # ── Bind mDNS callbacks now that UI is ready ──
        def on_device_found(name, ip, port):
            def _try_connect():
                for attempt in range(4):
                    if connect_wifi_device(f"{ip}:{port}"):
                        refresh_devices()
                        status_text.value = f"📡 {name}"
                        try:
                            page.update()
                        except Exception:
                            pass
                        threading.Thread(target=animate_device_card_found, daemon=True).start()
                        return
                    time.sleep(3)
            threading.Thread(target=_try_connect, daemon=True).start()

        def on_device_lost(name):
            refresh_devices()

        _wifi_discovery.on_device_found = on_device_found
        _wifi_discovery.on_device_lost = on_device_lost

        # ── Process devices found before callbacks were bound ──
        already_found = _wifi_discovery.get_found_devices()
        if already_found:
            for name, (ip, port) in already_found.items():
                on_device_found(name.split(".")[0], ip, port)

    threading.Thread(target=start_animations, daemon=True).start()


if __name__ == "__main__" or getattr(sys, 'frozen', False):
    # Check if launched as debug panel subprocess
    if len(sys.argv) > 1 and sys.argv[1] == "--flet-panel":
        try:
            from debug_mod import AdvancedControlPanel
            serial = sys.argv[2] if len(sys.argv) > 2 else None
            mode = sys.argv[3] if len(sys.argv) > 3 else "standard"
            port = sys.argv[4] if len(sys.argv) > 4 else None
            if serial:
                panel = AdvancedControlPanel(serial, mode=mode, is_overlay=True, ipc_port=port)
                ft.app(target=panel._main)
        except Exception as e:
            print(f"Debug panel error: {e}")
    else:
        # Normal UI launch
        ft.app(target=main)