"""
dialogs.py — All dialog windows for scrcpy UI
Contains: help, shortcuts, settings, about
"""

import flet as ft
import subprocess


# ==================== HELPERS ====================

def close_dialog(page: ft.Page, dialog: ft.AlertDialog):
    dialog.open = False
    page.update()


def _close_btn(page: ft.Page, on_click):
    """Animated close button: rotates 90° and turns red on hover."""
    is_light = page.theme_mode == ft.ThemeMode.LIGHT
    base = ft.colors.BLACK if is_light else ft.colors.WHITE
    icon = ft.Icon(ft.icons.CLOSE, size=20, color=ft.colors.with_opacity(0.5, base))
    def on_hover(e):
        e.control.rotate = ft.Rotate(angle=1.5708 if e.data == "true" else 0, alignment=ft.alignment.center)
        icon.color = ft.colors.RED_400 if e.data == "true" else ft.colors.with_opacity(0.5, base)
        page.update()
    return ft.Container(
        content=icon, width=32, height=32, border_radius=16,
        alignment=ft.alignment.center, ink=True,
        rotate=ft.Rotate(angle=0, alignment=ft.alignment.center),
        animate_rotation=ft.Animation(250, ft.AnimationCurve.EASE_IN_OUT),
        on_click=on_click, on_hover=on_hover,
    )


def _section_label(text: str, page: ft.Page = None):
    """Small uppercase section label."""
    is_light = page is not None and page.theme_mode == ft.ThemeMode.LIGHT
    base = ft.colors.BLACK if is_light else ft.colors.WHITE
    return ft.Text(
        text.upper(),
        size=10,
        weight=ft.FontWeight.BOLD,
        color=ft.colors.with_opacity(0.45, base),
    )


# ==================== HELP ====================

def _parse_body_blocks(body: str) -> list[tuple[str, str]]:
    """Split section body into blocks: ('md', text) or ('nav', text).
    Nav blocks are delimited by :::nav ... :::
    """
    import re
    blocks = []
    parts = re.split(r':::nav\n(.*?):::', body, flags=re.DOTALL)
    for i, part in enumerate(parts):
        if part.strip():
            kind = "nav" if i % 2 == 1 else "md"
            blocks.append((kind, part.strip()))
    return blocks if blocks else [("md", body)]


def _parse_help_sections(content: str) -> list[tuple[str, list]]:
    """Split help markdown into sections by ## headings.
    Returns list of (title, blocks) where blocks = [('md'|'nav', text), ...]
    """
    import re
    parts = re.split(r'^(## .+)$', content, flags=re.MULTILINE)
    sections = []
    preamble = parts[0]
    for i in range(1, len(parts) - 1, 2):
        title = parts[i].lstrip('#').strip()
        body  = (preamble + parts[i] + parts[i + 1]) if i == 1 else (parts[i] + parts[i + 1])
        preamble = ""
        sections.append((title, _parse_body_blocks(body.strip())))
    return sections if sections else [("Help", [("md", content)])]


def show_help_dialog(page: ft.Page, lang, load_help_content):
    help_content = load_help_content(lang.current_lang)
    dialog_ref   = [None]

    is_light       = page.theme_mode == ft.ThemeMode.LIGHT
    gradient_start = ft.colors.with_opacity(0.2, ft.colors.CYAN)
    gradient_end   = ft.colors.with_opacity(0.05, ft.colors.CYAN)
    border_color   = ft.colors.with_opacity(0.5, ft.colors.CYAN)
    text_color     = ft.colors.BLUE_GREY_900 if is_light else ft.colors.CYAN_50

    md_style = ft.MarkdownStyleSheet(
        blockquote_text_style=ft.TextStyle(
            font_family="CustomFont",
            italic=True,
            color=text_color,
        ),
        blockquote_decoration=ft.BoxDecoration(
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=[gradient_start, gradient_end],
            ),
            border=ft.border.all(1, border_color),
            border_radius=ft.border_radius.all(5),
        ),
        blockquote_padding=ft.padding.all(10),
    )

    code_style = ft.MarkdownStyleSheet(
        codeblock_decoration=ft.BoxDecoration(
            bgcolor=ft.colors.with_opacity(0.06, ft.colors.BLACK) if is_light else ft.colors.with_opacity(0.85, ft.colors.GREY_900),
            border_radius=8,
        ),
        codeblock_padding=ft.padding.all(12),
    )
    code_theme = ft.MarkdownCodeTheme.GITHUB if is_light else ft.MarkdownCodeTheme.ATOM_ONE_DARK

    sections = _parse_help_sections(help_content)

    # Build title→index map for nav links
    title_to_idx = {title: i for i, (title, _) in enumerate(sections)}

    # ── State ────────────────────────────────────────────────────────
    menu_open = [False]

    def _make_nav_item(line: str) -> ft.Control:
        """Parse a nav line 'icon text → Section Title' into a clickable row."""
        import re
        match = re.match(r'^(.*?)→\s*(.+)$', line)
        if match:
            label = match.group(1).strip()
            target = match.group(2).strip()
            idx = title_to_idx.get(target)
            def _on_click(_, idx=idx):
                if idx is not None:
                    content_col.scroll_to(key=f"section_{idx}", duration=300)
            return ft.Container(
                content=ft.Text(f"{label} →  {target}", size=13),
                on_click=_on_click,
                ink=True,
                border_radius=6,
                padding=ft.padding.symmetric(horizontal=8, vertical=6),
            )
        return ft.Text(line, size=13)

    def _make_nav_block(text: str) -> ft.Control:
        """Render :::nav block as left-bordered container with clickable items."""
        lines = [l for l in text.splitlines() if l.strip()]
        return ft.Container(
            content=ft.Column([_make_nav_item(line) for line in lines], spacing=2),
            border=ft.border.only(left=ft.BorderSide(3, ft.colors.ORANGE_400)),
            padding=ft.padding.only(left=12, top=8, bottom=8, right=8),
        )

    def _make_section_widget(i: int, blocks: list) -> ft.Column:
        """Build a Column of md/nav controls for one section."""
        controls = []
        for kind, text in blocks:
            if kind == "nav":
                controls.append(_make_nav_block(text))
            else:
                controls.append(ft.Markdown(
                    text,
                    selectable=True,
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    on_tap_link=lambda e: page.launch_url(e.data),
                    md_style_sheet=md_style,
                    code_theme=code_theme,
                    code_style_sheet=code_style,
                ))
        return ft.Column(controls, key=f"section_{i}", spacing=8, tight=True)

    # ── Per-section widgets with keys for scroll_to ──────────────────
    section_widgets = [
        _make_section_widget(i, blocks)
        for i, (_, blocks) in enumerate(sections)
    ]
    content_col = ft.Column(
        section_widgets,
        scroll=ft.ScrollMode.AUTO,
        height=560,
    )

    # ── Sections menu view ───────────────────────────────────────────
    def make_section_btn(idx: int, title: str):
        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.icons.ARTICLE_OUTLINED, size=16,
                        color=ft.colors.with_opacity(0.5, ft.colors.CYAN)),
                ft.Text(title, size=13),
            ], spacing=10),
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            border_radius=8,
            ink=True,
            on_click=_on_section_click(idx),
            bgcolor=ft.colors.TRANSPARENT,
        )

    def _on_section_click(idx: int):
        def _handler(_):
            menu_open[0]        = False
            content_col.visible = True
            menu_col.visible    = True  # AnimatedSwitcher requires visible=True
            switcher.content    = content_col
            toggle_btn.icon = ft.icons.MENU
            page.update()
            content_col.scroll_to(key=f"section_{idx}", duration=300)
        return _handler

    menu_col = ft.Column(
        [make_section_btn(i, title) for i, (title, _) in enumerate(sections)],
        scroll=ft.ScrollMode.AUTO,
        height=560,
        spacing=2,
    )

    # ── Toggle button ────────────────────────────────────────────────
    def on_toggle(_):
        menu_open[0] = not menu_open[0]
        if menu_open[0]:
            menu_col.visible    = True
            content_col.visible = True  # AnimatedSwitcher requires visible=True
            switcher.content    = menu_col
            toggle_btn.icon     = ft.icons.MENU_OPEN
        else:
            content_col.visible = True
            menu_col.visible    = True  # AnimatedSwitcher requires visible=True
            switcher.content    = content_col
            toggle_btn.icon = ft.icons.MENU
        page.update()

    switcher = ft.AnimatedSwitcher(
        content=content_col,
        transition=ft.AnimatedSwitcherTransition.FADE,
        duration=200,
        reverse_duration=150,
        switch_in_curve=ft.AnimationCurve.EASE_IN,
        switch_out_curve=ft.AnimationCurve.EASE_OUT,
    )

    toggle_btn = ft.IconButton(
        icon=ft.icons.MENU,
        icon_size=18,
        icon_color=ft.colors.with_opacity(0.6, ft.colors.BLACK if is_light else ft.colors.WHITE),
        tooltip=lang.t("help"),
        on_click=on_toggle,
        style=ft.ButtonStyle(
            padding=ft.padding.all(4),
            overlay_color=ft.colors.with_opacity(0.08, ft.colors.BLACK if is_light else ft.colors.WHITE),
        ),
    )

    # ── Dialog ───────────────────────────────────────────────────────
    dialog = ft.AlertDialog(
        title=ft.Row(
            [
                toggle_btn,
                ft.Text(lang.t("help"), size=16, weight=ft.FontWeight.BOLD, expand=True),
                _close_btn(page, lambda _: close_dialog(page, dialog_ref[0])),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=switcher,
        content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
        title_padding=ft.padding.only(left=8, top=12, right=8, bottom=4),
        actions=[],
        actions_padding=ft.padding.all(0),
    )
    dialog_ref[0] = dialog
    page.overlay.append(dialog)
    dialog.open = True
    page.update()


# ==================== SHORTCUTS ====================

def show_shortcuts_dialog(page: ft.Page, lang):
    dialog_ref = [None]
    blue = ft.colors.BLUE
    is_light = page.theme_mode == ft.ThemeMode.LIGHT
    base = ft.colors.BLACK if is_light else ft.colors.WHITE
    key_text_color = ft.colors.BLUE_900 if is_light else ft.colors.BLUE_50

    KEY_W = 36   # fixed width for every single keycap
    KEY_H = 28   # fixed height for every single keycap

    # ── Helper: one keycap (ref-based so hover can brighten it) ──
    def key(text: str):
        return ft.Container(
            content=ft.Text(
                text, size=11, weight=ft.FontWeight.BOLD,
                font_family="monospace", color=key_text_color,
                text_align=ft.TextAlign.CENTER,
            ),
            width=KEY_W,
            height=KEY_H,
            alignment=ft.alignment.center,
            bgcolor=ft.colors.with_opacity(0.15, blue),
            border=ft.border.all(1, ft.colors.with_opacity(0.3, blue)),
            border_radius=6,
        )

    # ── Helper: keys block (left side) ──
    def keys_block(*ks):
        parts = []
        for i, k in enumerate(ks):
            parts.append(key(k))
            if i < len(ks) - 1:
                parts.append(
                    ft.Text("+", size=12,
                            color=ft.colors.with_opacity(0.5, base),
                            width=10, text_align=ft.TextAlign.CENTER)
                )
        return ft.Row(parts, spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    # ── Helper: one shortcut row ──
    def row(icon, label, *keys_args):
        accent_bar = ft.Container(width=3, height=28, border_radius=2,
                                  bgcolor=ft.colors.TRANSPARENT)
        row_icon   = ft.Icon(icon, size=16, color=ft.colors.with_opacity(0.6, blue))
        keys_row   = keys_block(*keys_args)

        def on_hover(e):
            hovered = e.data == "true"
            # 1. Left accent strip
            accent_bar.bgcolor = ft.colors.with_opacity(0.7, blue) if hovered else ft.colors.TRANSPARENT
            # 2. Icon brightness / Opacity
            row_icon.color = ft.colors.with_opacity(1.0 if hovered else 0.6, blue)
            # 3. Keycap highlighting / Glow effect
            for ctrl in keys_row.controls:
                if isinstance(ctrl, ft.Container):
                    ctrl.bgcolor = ft.colors.with_opacity(0.3 if hovered else 0.15, blue)
                    ctrl.border  = ft.border.all(1, ft.colors.with_opacity(0.6 if hovered else 0.3, blue))
            page.update()

        return ft.Container(
            content=ft.Row(
                [
                    accent_bar,
                    # LEFT: fixed-width keys area so all rows align
                    ft.Container(content=keys_row, width=100),
                    # RIGHT: icon + label
                    ft.Row([row_icon, ft.Text(label, size=13)], spacing=8, expand=True),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=ft.padding.symmetric(vertical=4, horizontal=6),
            border_radius=8,
            on_hover=on_hover,
        )

    content = ft.Column(
        [
            _section_label(lang.t("shortcuts_screen"), page),
            row(ft.icons.FULLSCREEN,         lang.t("shortcut_fullscreen"), "Alt", "F"),
            row(ft.icons.MOBILE_OFF,         lang.t("shortcut_screen_off"), "Alt", "O"),
            row(ft.icons.POWER_SETTINGS_NEW, lang.t("shortcut_power"),      "Alt", "P"),

            ft.Divider(height=16, color=ft.colors.with_opacity(0.1, base)),

            _section_label(lang.t("shortcuts_window"), page),
            row(ft.icons.ASPECT_RATIO,       lang.t("shortcut_resize"),     "Alt", "G"),
            row(ft.icons.FIT_SCREEN,         lang.t("shortcut_fit"),        "Alt", "W"),

            ft.Divider(height=16, color=ft.colors.with_opacity(0.1, base)),

            _section_label(lang.t("shortcuts_navigation"), page),
            row(ft.icons.VOLUME_UP,          lang.t("shortcut_volume_up"),  "Alt", "↑"),
            row(ft.icons.VOLUME_DOWN,        lang.t("shortcut_volume_down"),"Alt", "↓"),
            row(ft.icons.HOME,               lang.t("shortcut_home"),       "Alt", "H"),
            row(ft.icons.ARROW_BACK,         lang.t("shortcut_back"),       "Alt", "B"),

            ft.Container(height=10),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.icons.WARNING_AMBER_ROUNDED, color=ft.colors.AMBER_700, size=20),
                    ft.Text(
                        lang.t("shortcuts_warning"),
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=ft.colors.AMBER_900 if is_light else ft.colors.AMBER_100,
                        expand=True,
                    ),
                ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=ft.colors.with_opacity(0.15 if is_light else 0.12, ft.colors.AMBER),
                padding=ft.padding.symmetric(horizontal=14, vertical=10),
                border_radius=8,
                border=ft.border.all(1.5, ft.colors.with_opacity(0.5 if is_light else 0.4, ft.colors.AMBER_600)),
            )
        ],
        width=420,
        scroll=ft.ScrollMode.AUTO,
    )

    dialog = ft.AlertDialog(
        # The title now contains the string: [Icon+Text] <---space---> [Cross]
        title=ft.Row(
            [
                ft.Row([
                    ft.Icon(ft.icons.KEYBOARD, size=20, color=blue),
                    ft.Text(lang.t("shortcuts_title"), size=16, weight=ft.FontWeight.BOLD)
                ], spacing=10),
                
                _close_btn(page, lambda _: close_dialog(page, dialog_ref[0])),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        ),
        title_padding=ft.padding.only(left=20, top=10, right=10, bottom=0),
        content=content,
        content_padding=ft.padding.symmetric(horizontal=20, vertical=10),
        actions=[],
    )
    dialog_ref[0] = dialog
    page.overlay.append(dialog)
    dialog.open = True
    page.update()


# ==================== SETTINGS ====================

def show_settings_dialog(page: ft.Page, lang, settings):
    is_light = page.theme_mode == ft.ThemeMode.LIGHT
    base     = ft.colors.BLACK if is_light else ft.colors.WHITE
    CYAN     = ft.colors.CYAN_400

    sw_extended     = ft.Switch(value=settings.get("extended_metrics", False),  active_color=CYAN, inactive_thumb_color=ft.colors.with_opacity(0.4, base))
    sw_hide_console = ft.Switch(value=settings.get("hide_console", True),        active_color=CYAN, inactive_thumb_color=ft.colors.with_opacity(0.4, base))
    sw_kill_adb     = ft.Switch(value=settings.get("kill_adb_on_exit", True),    active_color=CYAN, inactive_thumb_color=ft.colors.with_opacity(0.4, base))

    settings_dialog = None  # forward ref

    def save_settings(_):
        settings.set("extended_metrics",  sw_extended.value)
        settings.set("hide_console",      sw_hide_console.value)
        settings.set("kill_adb_on_exit",  sw_kill_adb.value)
        close_dialog(page, settings_dialog)

    def toggle_row(icon, title, desc, switch):
        def on_click(_):
            switch.value = not switch.value
            page.update()
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=18, color=ft.colors.with_opacity(0.7, CYAN)),
                ft.Column([
                    ft.Text(title, size=13, weight=ft.FontWeight.W_500),
                    ft.Text(desc, size=11, color=ft.colors.with_opacity(0.45, base)),
                ], spacing=1, tight=True, expand=True),
                switch,
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=8, ink=True, on_click=on_click,
            bgcolor=ft.colors.with_opacity(0.03, base),
            border=ft.border.all(1, ft.colors.with_opacity(0.07, base)),
        )

    def section_card(label_key, rows):
        return ft.Container(
            content=ft.Column([_section_label(lang.t(label_key), page), ft.Container(height=4)] + rows, spacing=6, tight=True),
            padding=ft.padding.all(12),
            border_radius=10,
            bgcolor=ft.colors.with_opacity(0.025 if is_light else 0.04, base),
        )

    settings_content = ft.Column([
        section_card("settings_debug",
            [toggle_row(ft.icons.BUG_REPORT_OUTLINED, lang.t("settings_extended"), lang.t("settings_extended_desc"), sw_extended)],
        ),
        section_card("settings_behavior",
            [
                toggle_row(ft.icons.TERMINAL_OUTLINED,  lang.t("settings_hide_console"), "", sw_hide_console),
                toggle_row(ft.icons.POWER_SETTINGS_NEW, lang.t("settings_kill_adb"),     "", sw_kill_adb),
            ],
        ),
    ], spacing=10, tight=True, width=360)

    settings_dialog = ft.AlertDialog(
        title=ft.Row(
            [
                ft.Icon(ft.icons.SETTINGS, size=20, color=CYAN),
                ft.Text(lang.t("settings_title"), size=16, weight=ft.FontWeight.BOLD, expand=True),
                _close_btn(page, save_settings),
            ],
            spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        title_padding=ft.padding.only(left=16, top=12, right=8, bottom=4),
        content=settings_content,
        content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
        actions=[], actions_padding=ft.padding.all(0),
    )
    page.overlay.append(settings_dialog)
    settings_dialog.open = True
    page.update()


# ==================== ABOUT ====================

def _get_scrcpy_version() -> str:
    """Try to get the installed scrcpy version."""
    try:
        import sys
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            from localization import SCRCPY
        except ImportError:
            SCRCPY = "scrcpy"
        result = subprocess.run(
            [SCRCPY, "--version"],
            capture_output=True, text=True, timeout=3,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        for line in result.stdout.splitlines():
            if line.strip().startswith("scrcpy"):
                parts = line.strip().split()
                for p in parts[1:]:
                    if p and not p.startswith("http") and not p.startswith("<"):
                        return p
    except Exception:
        pass
    return "—"


def show_about_dialog(page: ft.Page, lang):
    scrcpy_version = _get_scrcpy_version()
    accent = ft.colors.CYAN_400
    dialog_ref = [None]  # forward ref for close button
    is_light = page.theme_mode == ft.ThemeMode.LIGHT
    base = ft.colors.BLACK if is_light else ft.colors.WHITE

    def t(key: str) -> str:
        return lang.t(key)

    # ── Helper: icon + text row ────────────────────────────────────
    def info_row(icon, label: str, value: str, value_color=None):
        return ft.Row(
            [
                ft.Icon(icon, size=16, color=ft.colors.with_opacity(0.5, base)),
                ft.Text(label, size=12, color=ft.colors.with_opacity(0.55, base), width=90),
                ft.Text(value, size=12, weight=ft.FontWeight.W_500,
                        color=value_color or (ft.colors.BLACK if is_light else ft.colors.WHITE)),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # ── Helper: compact link button ────────────────────────
    def link_btn(label: str, url: str, icon_name=ft.icons.OPEN_IN_NEW, color=None):
        btn_color = color or accent
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon_name, size=13, color=btn_color),
                    ft.Text(label, size=12, color=btn_color, weight=ft.FontWeight.W_500),
                ],
                spacing=4,
                tight=True,
            ),
            on_click=lambda _: page.launch_url(url),
            padding=ft.padding.symmetric(horizontal=8, vertical=5),
            border_radius=6,
            border=ft.border.all(1, ft.colors.with_opacity(0.25, btn_color)),
        )

    # ── Styled card — matches main UI + top accent bar ────────────
    def section_card(content, accent_color):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        height=3,
                        border_radius=ft.border_radius.only(top_left=12, top_right=12),
                        gradient=ft.LinearGradient(
                            begin=ft.alignment.center_left,
                            end=ft.alignment.center_right,
                            colors=[
                                ft.colors.with_opacity(0.85, accent_color),
                                ft.colors.with_opacity(0.15, accent_color),
                            ],
                        ),
                    ),
                    ft.Container(
                        content=content,
                        padding=ft.padding.symmetric(horizontal=14, vertical=10),
                    ),
                ],
                spacing=0,
                tight=True,
            ),
            border_radius=12,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=[
                    ft.colors.with_opacity(0.05, base),
                    ft.colors.with_opacity(0.01, base),
                ],
            ),
            border=ft.border.all(1, ft.colors.with_opacity(0.1, base)),
            shadow=ft.BoxShadow(
                spread_radius=1, blur_radius=5,
                color=ft.colors.with_opacity(0.15 if is_light else 0.3, ft.colors.BLACK),
                offset=ft.Offset(0, 4),
            ),
        )

    # ── Section: GUI  (cyan) ──────────────────────────────────────
    gui_card = section_card(
        accent_color=ft.colors.CYAN_400,
        content=ft.Column(
            [
                _section_label(t("about_gui_section"), page),
                ft.Container(height=4),
                ft.Row(
                    [
                        ft.Icon(ft.icons.PHONELINK, size=24, color=accent),
                        ft.Column(
                            [
                                ft.Text("scrcpy UI", size=16, weight=ft.FontWeight.BOLD),
                                ft.Text(t("about_gui_desc"), size=11,
                                        color=ft.colors.with_opacity(0.5, base)),
                            ],
                            spacing=1, tight=True,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=6),
                info_row(ft.icons.PERSON_OUTLINE,  t("about_author"), "Rafik Akhmedov"),
                info_row(ft.icons.ALTERNATE_EMAIL, "GitHub",          "Sfix0"),
            ],
            spacing=3, tight=True,
        ),
    )

    # ── Section: scrcpy  (green) ──────────────────────────────────
    scrcpy_card = section_card(
        accent_color=ft.colors.GREEN_400,
        content=ft.Column(
            [
                _section_label(t("about_based_on"), page),
                ft.Container(height=4),
                ft.Row(
                    [
                        ft.Icon(ft.icons.ANDROID, size=24, color=ft.colors.GREEN_400),
                        ft.Column(
                            [
                                ft.Text("scrcpy", size=16, weight=ft.FontWeight.BOLD),
                                ft.Text("Genymobile / Romain Vimont", size=11,
                                        color=ft.colors.with_opacity(0.5, base)),
                            ],
                            spacing=1, tight=True,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=6),
                info_row(ft.icons.TAG,           t("about_version"), scrcpy_version, ft.colors.GREEN_300 if not is_light else ft.colors.GREEN_700),
                info_row(ft.icons.GAVEL_ROUNDED, t("about_license"), "Apache 2.0"),
                ft.Container(height=8),
                ft.Row(
                    [
                        link_btn("GitHub", "https://github.com/Genymobile/scrcpy", ft.icons.CODE),
                        link_btn(t("about_donate"), "https://liberapay.com/rom1v/",
                                 ft.icons.FAVORITE_BORDER, ft.colors.PINK_300 if not is_light else ft.colors.PINK_700),
                    ],
                    spacing=8,
                ),
            ],
            spacing=3, tight=True,
        ),
    )

    # ── Section: Framework  (indigo) ─────────────────────────────
    flet_card = section_card(
        accent_color=ft.colors.INDIGO_400,
        content=ft.Column(
            [
                _section_label(t("about_framework_section"), page),
                ft.Container(height=4),
                ft.Row(
                    [
                        ft.Icon(ft.icons.DEVELOPER_BOARD, size=26, color=ft.colors.INDIGO_300 if not is_light else ft.colors.INDIGO_700),
                        ft.Column(
                            [
                                ft.Text("Flet", size=16, weight=ft.FontWeight.BOLD),
                                ft.Text("AppVeyor / Feodor Fitsner", size=11,
                                        color=ft.colors.with_opacity(0.5, base)),
                            ],
                            spacing=1, tight=True,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=6),
                info_row(ft.icons.TAG,           t("about_version"), "0.24.1", ft.colors.INDIGO_300 if not is_light else ft.colors.INDIGO_700),
                info_row(ft.icons.GAVEL_ROUNDED, t("about_license"), "Apache 2.0"),
                ft.Container(height=8),
                link_btn("flet.dev", "https://flet.dev", ft.icons.LANGUAGE, ft.colors.INDIGO_300 if not is_light else ft.colors.INDIGO_700),
            ],
            spacing=3, tight=True,
        ),
    )

    # ── Section: Font  (amber) ────────────────────────────────────
    font_card = section_card(
        accent_color=ft.colors.AMBER_400,
        content=ft.Column(
            [
                _section_label(t("about_font_section"), page),
                ft.Container(height=4),
                ft.Row(
                    [
                        ft.Icon(ft.icons.TEXT_FIELDS, size=24, color=ft.colors.AMBER_300 if not is_light else ft.colors.AMBER_700),
                        ft.Column(
                            [
                                ft.Text("e-Ukraine Light", size=16,
                                        weight=ft.FontWeight.BOLD, font_family="CustomFont"),
                                ft.Text("Dmytro Rastvortsev / Fedoriv", size=11,
                                        color=ft.colors.with_opacity(0.5, base)),
                            ],
                            spacing=1, tight=True,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=6),
                info_row(ft.icons.GAVEL_ROUNDED, t("about_license"), "CC BY 4.0"),
                ft.Container(height=8),
                ft.Row(
                    [
                        link_btn("Official", "https://thedigital.gov.ua/fonts", ft.icons.LANGUAGE, ft.colors.AMBER_300 if not is_light else ft.colors.AMBER_700),
                        link_btn("Wikipedia", "https://en.wikipedia.org/wiki/E-Ukraine", ft.icons.INFO_OUTLINE, ft.colors.AMBER_200 if not is_light else ft.colors.AMBER_800),
                    ],
                    spacing=8,
                ),
            ],
            spacing=3, tight=True,
        ),
    )

    # ── Assemble ──────────────────────────────────────────────────
    content = ft.Column(
        [
            gui_card,
            ft.Container(height=8),
            scrcpy_card,
            ft.Container(height=8),
            flet_card,
            ft.Container(height=8),
            font_card,
        ],
        scroll=ft.ScrollMode.HIDDEN,
        height=580,
        spacing=0,
    )

    dialog = ft.AlertDialog(
        title=ft.Row(
            [
                ft.Icon(ft.icons.INFO_OUTLINE, size=18, color=accent),
                ft.Text(t("about_title"), size=16, weight=ft.FontWeight.BOLD, expand=True),
                _close_btn(page, lambda _: close_dialog(page, dialog_ref[0])),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=content,
        content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
        title_padding=ft.padding.only(left=16, top=12, right=8, bottom=4),
        actions=[],
        actions_padding=ft.padding.all(0),
        inset_padding=ft.padding.symmetric(horizontal=20, vertical=24),
    )
    dialog_ref[0] = dialog
    page.overlay.append(dialog)
    dialog.open = True
    page.update()