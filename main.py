"""
Whisper Voice — тёмный минимализм (VS Code стиль)
pip install customtkinter pyaudio faster-whisper pyperclip keyboard pystray pillow
"""

import keyboard
import pyaudio
import wave
import pyperclip
import io
import time
import threading
import math
import json
import os
import re
import sys
from datetime import datetime
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem
import customtkinter as ctk

# ══════════════════════════════════════════════════════════════════════
#  ПАЛИТРА — точь-в-точь VS Code Dark+
# ══════════════════════════════════════════════════════════════════════
C = {
    "bg":        "#181825",
    "sidebar":   "#1e1e2e",
    "panel":     "#252535",
    "input":     "#313244",
    "hover":     "#2a2a3e",
    "active":    "#45475a",
    "border":    "#45475a",
    "text":      "#cdd6f4",
    "text_dim":  "#a6e3a1",
    "text_mute": "#89b4fa",
    "text_faint":"#6c7086",
    "accent":    "#cba6f7",
    "accent2":   "#94e2d5",
    "accent3":   "#fab387",
    "green":     "#a6e3a1",
    "red":       "#f38ba8",
    "yellow":    "#f9e2af",
    "orange":    "#fab387",
    "statusbar": "#1e1e2e",
    "statusbar_text": "#cdd6f4",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DICT_FILE  = os.path.join(SCRIPT_DIR, "dictionary.json")
SET_FILE   = os.path.join(SCRIPT_DIR, "settings.json")
LOG_FILE   = os.path.join(SCRIPT_DIR, "transcription_log.json")

# ══════════════════════════════════════════════════════════════════════
#  ОПРЕДЕЛЕНИЕ ЯЗЫКА ПО РАСКЛАДКЕ WINDOWS
# ══════════════════════════════════════════════════════════════════════

# Таблица: LCID раскладки → код языка Whisper
_LAYOUT_TO_LANG = {
    0x0419: "ru",  # Русский
    0x0422: "uk",  # Украинский
    0x0407: "de",  # Немецкий (Германия)
    0x0C07: "de",  # Немецкий (Австрия)
    0x0807: "de",  # Немецкий (Швейцария)
    0x0409: "en",  # Английский (США)
    0x0809: "en",  # Английский (Великобритания)
    0x0C09: "en",  # Английский (Австралия)
    0x1009: "en",  # Английский (Канада)
}

def get_keyboard_layout_lang() -> str | None:
    """Возвращает код языка Whisper по текущей раскладке клавиатуры Windows."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        thread_id = user32.GetWindowThreadProcessId(hwnd, 0)
        hkl = user32.GetKeyboardLayout(thread_id)
        lcid = hkl & 0xFFFF  # младшие 16 бит — LANGID
        return _LAYOUT_TO_LANG.get(lcid)
    except Exception:
        return None

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ══════════════════════════════════════════════════════════════════════
#  СЛОВАРЬ
# ══════════════════════════════════════════════════════════════════════

def load_dictionary() -> dict:
    if os.path.exists(DICT_FILE):
        with open(DICT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    d = {
        "RaDley":  ["радли", "редли", "radley", "рэдли"],
        "Legion":  ["легион", "legion"],
        "Python":  ["питон",  "пайтон"],
        "Whisper": ["вискер", "виспер"],
        "NVIDIA":  ["нвидиа", "нвидия"],
    }
    save_dictionary(d)
    return d

def save_dictionary(d: dict):
    with open(DICT_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

# ══════════════════════════════════════════════════════════════════════
#  ПОСТОЯННЫЕ ЛОГИ
# ══════════════════════════════════════════════════════════════════════

def load_log() -> list:
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_log(entries: list):
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

dictionary: dict = load_dictionary()

def apply_dictionary(text: str) -> str:
    for correct, variants in dictionary.items():
        for v in variants:
            text = re.sub(re.escape(v), correct, text, flags=re.IGNORECASE)
    return text

def get_hot_words() -> list:
    out = []
    for correct, variants in dictionary.items():
        out.append(correct)
        out.extend(variants)
    return out

# ══════════════════════════════════════════════════════════════════════
#  ТРЕЙ
# ══════════════════════════════════════════════════════════════════════

def make_tray_icon(phase: float, recording: bool) -> Image.Image:
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if not recording:
        draw.ellipse([22, 22, 42, 42], fill=(100, 100, 100, 200))
    else:
        r = 18 + int(math.sin(phase) * 5)
        t = (math.sin(phase) + 1) / 2
        col = (int(0 + 100 * t), int(122 + 50 * t), 204)
        draw.ellipse([32-r, 32-r, 32+r, 32+r], outline=col, width=2)
        draw.ellipse([20, 20, 44, 44], fill=(0, 122, 204, 230))
    return img

# ══════════════════════════════════════════════════════════════════════
#  ВИДЖЕТЫ-ХЕЛПЕРЫ
# ══════════════════════════════════════════════════════════════════════

def lbl(parent, text, size=12, color=None, bold=False, **kw):
    return ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont("Consolas", size + 2, "bold" if bold else "normal"),
        text_color=color or C["text"], **kw)

def vsbtn(parent, text, cmd, width=80, accent=False, danger=False, **kw):
    fg = C["accent"] if accent else (C["red"] if danger else C["input"])
    hv = "#005f9e" if accent else ("#c00" if danger else C["active"])
    return ctk.CTkButton(
        parent, text=text, command=cmd, width=width, height=34,
        font=ctk.CTkFont("Consolas", 13),
        fg_color=fg, hover_color=hv,
        text_color=C["text"], corner_radius=6, border_width=0, **kw)

def vsentry(parent, width=200, placeholder="", textvariable=None, **kw):
    return ctk.CTkEntry(
        parent, width=width,
        font=ctk.CTkFont("Consolas", 14),
        fg_color=C["input"], border_color=C["border"], border_width=1,
        text_color=C["text"],
        placeholder_text=placeholder,
        placeholder_text_color=C["text_faint"],
        corner_radius=6, textvariable=textvariable, **kw)

def vsep(parent, vertical=False):
    if vertical:
        return ctk.CTkFrame(parent, width=1, fg_color=C["border"])
    return ctk.CTkFrame(parent, height=1, fg_color=C["border"])

def vsoption(parent, variable, values, width=150):
    return ctk.CTkOptionMenu(
        parent, variable=variable, values=values, width=width,
        font=ctk.CTkFont("Consolas", 13),
        fg_color=C["input"], button_color=C["input"],
        button_hover_color=C["active"],
        dropdown_fg_color=C["panel"],
        dropdown_hover_color=C["active"],
        text_color=C["text"], dropdown_text_color=C["text"],
        corner_radius=6)

# ══════════════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ОКНО
# ══════════════════════════════════════════════════════════════════════

class WhisperApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Whisper Voice")
        self.geometry("1100x720")
        self.minsize(860, 580)
        self.configure(fg_color=C["bg"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.model          = None
        self.recording      = False
        self._phase         = 0.0
        self.hotkey_ref     = None
        self.settings       = self._load_settings()
        self._total_count   = 0
        self._total_words   = 0
        self._tray_rec      = False
        self._tray_running  = True
        self._current_tab   = "log"
        self._log_entries   = load_log()   # загружаем постоянные логи
        self._editing_word  = None

        # Микрофон — мониторинг
        self._mic_level     = 0.0          # 0.0 … 1.0
        self._mic_monitor_running = False
        self._mic_monitor_thread  = None
        self._mic_device_index    = None   # None = системный по умолчанию

        LANG_LABELS = {
            "auto":             "🌐 Авто (Whisper)",
            "keyboard_layout":  "⌨️  По раскладке",
            "ru":               "🇷🇺 Русский",
            "uk":               "🇺🇦 Украинский",
            "de":               "🇩🇪 Немецкий",
            "en":               "🇬🇧 Английский",
        }

        # ── ИСПРАВЛЕНИЕ: pystray передаёт item как первый аргумент в callback ──
        def make_lang_item(code, label):
            def action(item, c=code):   # ← item обязателен, иначе c получит объект MenuItem
                self._set_lang_from_tray(c)
            def checked(item, c=code):
                return self.settings.get("language") == c
            return MenuItem(label, action, checked=checked, radio=True)

        self._tray_icon = Icon(
            "whisper", make_tray_icon(0, False), "Whisper Voice",
            menu=Menu(
                MenuItem("Открыть", lambda item: self._show_from_tray()),
                Menu.SEPARATOR,
                MenuItem("Язык", Menu(
                    *[make_lang_item(c, l) for c, l in LANG_LABELS.items()]
                )),
                Menu.SEPARATOR,
                MenuItem("Выход", lambda item: self._quit_app())))
        threading.Thread(target=self._tray_thread, daemon=True).start()

        self._build_ui()
        self._register_hotkey()
        self._load_model_async()
        self._start_mic_monitor()
        self._animate()

    # ── Настройки ────────────────────────────────────────────────────

    def _load_settings(self) -> dict:
        d = {"hotkey": "win+ctrl", "language": "auto",
             "beam_size": 5, "min_dur": 0.5,
             "device": "cuda", "compute": "float16",
             "whisper_model": "turbo", "mic_device_index": None}
        if os.path.exists(SET_FILE):
            with open(SET_FILE, "r", encoding="utf-8") as f:
                d.update(json.load(f))
        return d

    def _save_settings(self):
        with open(SET_FILE, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    # ══════════════════════════════════════════════════════════════════
    #  UI
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── Activity Bar ──────────────────────────────────────────────
        self.activity = ctk.CTkFrame(self, width=56, fg_color=C["sidebar"],
                                      corner_radius=0)
        self.activity.pack(side="left", fill="y")
        self.activity.pack_propagate(False)

        self._act_btns = {}
        for i, (ico, key) in enumerate([("📋", "log"), ("📖", "dict"), ("⚙", "settings")]):
            f = ctk.CTkFrame(self.activity, width=56, height=56,
                              fg_color="transparent", cursor="hand2")
            f.pack(pady=(12 if i == 0 else 2, 0))
            f.pack_propagate(False)
            lb = ctk.CTkLabel(f, text=ico,
                               font=ctk.CTkFont("Segoe UI Emoji", 22),
                               text_color=C["text_faint"], cursor="hand2")
            lb.place(relx=0.5, rely=0.5, anchor="center")
            for w in (f, lb):
                w.bind("<Button-1>", lambda e, k=key: self._switch_tab(k))
            lb.bind("<Enter>", lambda e, w=lb: w.configure(text_color=C["text"]))
            lb.bind("<Leave>", lambda e, w=lb, k=key: w.configure(
                text_color=C["text"] if self._current_tab == k else C["text_faint"]))
            self._act_btns[key] = lb

        # ── Sidebar ───────────────────────────────────────────────────
        self.sidebar = ctk.CTkFrame(self, width=240, fg_color=C["sidebar"],
                                     corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        vsep(self.sidebar).pack(fill="x")

        self._sidebar_title = lbl(self.sidebar, "ЛОГ", 11,
                                   color=C["text_faint"], bold=True)
        self._sidebar_title.pack(anchor="w", padx=12, pady=(10, 8))

        # Счётчики
        self._stat_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self._stat_frame.pack(fill="x", padx=8, pady=(0, 8))
        self._sb_count = self._sidebar_stat("0", "записей")
        self._sb_words = self._sidebar_stat("0", "слов")
        self._sb_lang  = self._sidebar_stat("—", "последний язык")

        vsep(self.sidebar).pack(fill="x", padx=8)

        self._model_lbl = lbl(self.sidebar, "⟳ загрузка...", 12,
                               color=C["yellow"])
        self._model_lbl.pack(anchor="w", padx=12, pady=(8, 4))

        self._rec_lbl = lbl(self.sidebar, "● ожидание", 12,
                             color=C["text_faint"])
        self._rec_lbl.pack(anchor="w", padx=12)

        self._hk_lbl = lbl(self.sidebar, self.settings["hotkey"].upper(),
                            12, color=C["text_mute"])
        self._hk_lbl.pack(anchor="w", padx=12, pady=(4, 0))

        vsep(self.sidebar).pack(fill="x", padx=8, pady=(12, 6))
        lbl(self.sidebar, "ЯЗЫК", 10, color=C["text_faint"], bold=True).pack(anchor="w", padx=12)
        self._lang_btns_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self._lang_btns_frame.pack(fill="x", padx=8, pady=(4, 0))
        self._build_lang_buttons()

        vsep(self.sidebar).pack(fill="x", padx=8, pady=(12, 6))
        lbl(self.sidebar, "УСТРОЙСТВО ВВОДА", 10, color=C["text_faint"], bold=True).pack(anchor="w", padx=12)

        # Комбо выбора микрофона
        self._mic_var = ctk.StringVar(value="По умолчанию")
        self._mic_combo = ctk.CTkOptionMenu(
            self.sidebar, variable=self._mic_var,
            values=["По умолчанию"],
            width=220,
            font=ctk.CTkFont("Consolas", 11),
            fg_color=C["input"], button_color=C["input"],
            button_hover_color=C["active"],
            dropdown_fg_color=C["panel"],
            dropdown_hover_color=C["active"],
            text_color=C["text"], dropdown_text_color=C["text"],
            corner_radius=6,
            command=self._on_mic_selected)
        self._mic_combo.pack(fill="x", padx=8, pady=(4, 2))
        self._refresh_mic_list()

        # Уровень сигнала
        lbl(self.sidebar, "Уровень сигнала", 10, color=C["text_faint"]).pack(anchor="w", padx=12, pady=(6, 2))
        self._mic_bar_canvas = ctk.CTkCanvas(
            self.sidebar, height=14, bg=C["sidebar"],
            highlightthickness=0)
        self._mic_bar_canvas.pack(fill="x", padx=8, pady=(0, 2))
        self._mic_bar_canvas.bind("<Configure>", self._redraw_mic_bar)

        self._mic_db_lbl = lbl(self.sidebar, "– dB", 10, color=C["text_faint"])
        self._mic_db_lbl.pack(anchor="w", padx=12)

        # Громкость микрофона (Windows only)
        lbl(self.sidebar, "Усиление входа", 10, color=C["text_faint"]).pack(anchor="w", padx=12, pady=(8, 2))
        self._mic_vol_var = ctk.DoubleVar(value=100.0)
        mic_vol_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        mic_vol_row.pack(fill="x", padx=8, pady=(0, 4))
        self._mic_vol_slider = ctk.CTkSlider(
            mic_vol_row, from_=0, to=100,
            variable=self._mic_vol_var,
            button_color=C["accent"],
            button_hover_color="#9b7fd4",
            progress_color="#6a4f9f",
            fg_color=C["input"],
            command=self._on_mic_vol_change)
        self._mic_vol_slider.pack(side="left", fill="x", expand=True)
        self._mic_vol_lbl = lbl(mic_vol_row, "100%", 10, color=C["accent3"], width=38)
        self._mic_vol_lbl.pack(side="left", padx=(4, 0))
        self._load_mic_volume()

        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(fill="y", expand=True)
        lbl(self.sidebar, "Whisper Voice  ", 9,
            color=C["text_faint"]).pack(pady=(0, 8), anchor="e")

        # ── Разделитель ───────────────────────────────────────────────
        vsep(self, vertical=True).pack(side="left", fill="y")

        # ── Основной контент ──────────────────────────────────────────
        self.main = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.main.pack(side="left", fill="both", expand=True)

        # Страницы
        self._pages = {}
        self._build_log_page()
        self._build_dict_page()
        self._build_settings_page()

        # Восстанавливаем сохранённые логи в UI
        for entry in self._log_entries:
            lang, now, text = entry
            is_sys = lang in ("sys", "ERR")
            if not is_sys:
                self._total_count += 1
                self._total_words += len(text.split())
            self._render_log_row(lang, now, text)
        self._sb_count.configure(text=str(self._total_count))
        self._sb_words.configure(text=str(self._total_words))
        if self._log_entries:
            last = [e for e in self._log_entries if e[0] not in ("sys", "ERR")]
            if last:
                self._sb_lang.configure(text=last[-1][0].upper())

        # Статус-бар
        self.statusbar = ctk.CTkFrame(self, height=28,
                                       fg_color=C["statusbar"], corner_radius=0)
        self.statusbar.pack(side="bottom", fill="x")
        self.statusbar.pack_propagate(False)
        lbl(self.statusbar, "  Whisper Voice", 12,
            color=C["statusbar_text"]).pack(side="left")
        self._sb_right = lbl(
            self.statusbar,
            f"{self.settings['device'].upper()} · {self.settings['compute']}  ",
            12, color=C["statusbar_text"])
        self._sb_right.pack(side="right")

        self._switch_tab("log")

    def _build_lang_buttons(self):
        for w in self._lang_btns_frame.winfo_children():
            w.destroy()
        langs = [("AUTO", "auto"), ("⌨", "keyboard_layout"), ("RU", "ru"), ("UK", "uk"), ("DE", "de"), ("EN", "en")]
        cur = self.settings.get("language", "auto")
        row = None
        for i, (label, code) in enumerate(langs):
            if i % 3 == 0:
                row = ctk.CTkFrame(self._lang_btns_frame, fg_color="transparent")
                row.pack(fill="x", pady=2)
            is_active = (code == cur)
            fg = C["accent"] if is_active else C["input"]
            hv = "#9b7fd4" if is_active else C["active"]
            btn = ctk.CTkButton(
                row, text=label, width=66, height=28,
                font=ctk.CTkFont("Consolas", 12, "bold" if is_active else "normal"),
                fg_color=fg, hover_color=hv,
                text_color=C["bg"] if is_active else C["text"],
                corner_radius=6, border_width=0,
                command=lambda c=code: self._set_lang_sidebar(c))
            btn.pack(side="left", padx=2)

    def _set_lang_sidebar(self, code: str):
        self.settings["language"] = code
        self._save_settings()
        try:
            self._s_lang.set(code)
        except Exception:
            pass
        self._build_lang_buttons()
        labels = {"auto": "АВТО", "keyboard_layout": "⌨ РАСКЛАДКА", "ru": "RU", "uk": "UK", "de": "DE", "en": "EN"}
        self._append_log("sys", f"язык: {labels.get(code, code)}")

    def _sidebar_stat(self, value, label_text):
        row = ctk.CTkFrame(self._stat_frame, fg_color="transparent")
        row.pack(fill="x", pady=1)
        v = lbl(row, value, 16, color=C["accent2"], bold=True)
        v.pack(side="left", padx=(4, 6))
        lbl(row, label_text, 12, color=C["text_faint"]).pack(side="left")
        return v

    # ══════════════════════════════════════════════════════════════════
    #  СТРАНИЦА: ЛОГ
    # ══════════════════════════════════════════════════════════════════

    def _build_log_page(self):
        page = ctk.CTkFrame(self.main, fg_color=C["bg"], corner_radius=0)
        self._pages["log"] = page

        tb = ctk.CTkFrame(page, height=36, fg_color=C["bg"], corner_radius=0)
        tb.pack(fill="x")
        tb.pack_propagate(False)
        vsep(tb).pack(side="bottom", fill="x")
        vsbtn(tb, "Копировать всё", self._copy_all_log, width=110
              ).pack(side="right", padx=4, pady=4)
        vsbtn(tb, "Очистить", self._clear_log, width=80
              ).pack(side="right", padx=(0, 4), pady=4)

        self._log_scroll = ctk.CTkScrollableFrame(
            page, fg_color=C["bg"], corner_radius=0,
            scrollbar_button_color=C["input"],
            scrollbar_button_hover_color=C["active"])
        self._log_scroll.pack(fill="both", expand=True)
        # NOTE: _log_entries already loaded in __init__ from disk

    def _append_log(self, lang: str, text: str):
        now    = datetime.now().strftime("%H:%M:%S")
        is_sys = lang in ("sys", "ERR")
        if not is_sys:
            self._total_count += 1
            self._total_words += len(text.split())
            self._sb_count.configure(text=str(self._total_count))
            self._sb_words.configure(text=str(self._total_words))
            self._sb_lang.configure(text=lang.upper())

        self._log_entries.append((lang, now, text))
        save_log(self._log_entries)

        self._render_log_row(lang, now, text)
        # Auto-scroll
        self._log_scroll._parent_canvas.yview_moveto(1.0)

    def _render_log_row(self, lang: str, now: str, text: str):
        """Render one log row in the scrollable frame."""
        is_sys = lang in ("sys", "ERR")
        # Row container
        row = ctk.CTkFrame(self._log_scroll, fg_color="transparent", corner_radius=4)
        row.pack(fill="x", padx=4, pady=1)
        row.bind("<Enter>", lambda e, r=row: r.configure(fg_color=C["hover"]))
        row.bind("<Leave>", lambda e, r=row: r.configure(fg_color="transparent"))

        # Timestamp (фиксированная ширина)
        time_lbl = ctk.CTkLabel(
            row, text=now, width=68,
            font=ctk.CTkFont("Consolas", 12),
            text_color=C["text_faint"], anchor="w")
        time_lbl.pack(side="left", padx=(6, 0))

        # Lang badge (фиксированная ширина)
        if not is_sys:
            badge_color = C["accent2"] if lang != "ERR" else C["red"]
            lang_lbl = ctk.CTkLabel(
                row, text=f"[{lang}]", width=42,
                font=ctk.CTkFont("Consolas", 12),
                text_color=badge_color, anchor="w")
            lang_lbl.pack(side="left", padx=(4, 0))

        # Text label (создаём, но НЕ пакуем сразу)
        text_color = C["text_dim"] if is_sys else (C["red"] if lang == "ERR" else C["text"])
        text_lbl = ctk.CTkLabel(
            row, text=text,
            font=ctk.CTkFont("Consolas", 13),
            text_color=text_color, anchor="w", justify="left")

        # ✅ 1. Сначала пакуем кнопку ВПРАВО. Tkinter сразу резервирует под неё место.
        if not is_sys:
            copy_btn = ctk.CTkLabel(
                row, text="⎘", width=24,
                font=ctk.CTkFont("Consolas", 14),
                text_color=C["text_faint"], cursor="hand2")
            copy_btn.pack(side="right", padx=(0, 6))
            copy_btn.bind("<Button-1>", lambda e, t=text: pyperclip.copy(t))
            copy_btn.bind("<Enter>", lambda e, w=copy_btn: w.configure(text_color=C["accent"]))
            copy_btn.bind("<Leave>", lambda e, w=copy_btn: w.configure(text_color=C["text_faint"]))

        # ✅ 2. Текст пакуем ПОСЛЕДНИМ. Он займёт только оставшееся пространство.
        text_lbl.pack(side="left", padx=(6, 0), fill="x", expand=True)

        # ✅ 3. Динамический расчёт wraplength при любом ресайзе
        def _update_wrap(evt):
            # evt.width — актуальная ширина строки
            # Вычитаем: время(~70) + язык(~45) + кнопка(~30) + отступы(~25)
            available = evt.width - 170
            if available > 50:  # Защита от отрицательных значений при узком окне
                text_lbl.configure(wraplength=available)
        row.bind("<Configure>", _update_wrap)

        # Auto-scroll
        self._log_scroll._parent_canvas.yview_moveto(1.0)

    def _clear_log(self):
        for w in self._log_scroll.winfo_children():
            w.destroy()
        self._log_entries.clear()
        save_log(self._log_entries)
        self._total_count = 0; self._total_words = 0
        self._sb_count.configure(text="0")
        self._sb_words.configure(text="0")
        self._sb_lang.configure(text="—")

    def _copy_all_log(self):
        lines = []
        for lang, now, text in self._log_entries:
            if lang in ("sys", "ERR"):
                lines.append(f"{now}  {text}")
            else:
                lines.append(f"{now}  [{lang}]  {text}")
        if lines:
            pyperclip.copy("\n".join(lines))

    # ══════════════════════════════════════════════════════════════════
    #  СТРАНИЦА: СЛОВАРЬ
    # ══════════════════════════════════════════════════════════════════

    def _build_dict_page(self):
        page = ctk.CTkFrame(self.main, fg_color=C["bg"], corner_radius=0)
        self._pages["dict"] = page

        form = ctk.CTkFrame(page, fg_color=C["sidebar"], corner_radius=0)
        form.pack(fill="x")
        vsep(form).pack(side="bottom", fill="x")

        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(padx=12, pady=10, fill="x")

        lbl(row, "Слово:", 11, color=C["text_faint"]).pack(side="left")
        self._dw = vsentry(row, 130, "RaDley")
        self._dw.pack(side="left", padx=(6, 16))

        lbl(row, "Варианты:", 11, color=C["text_faint"]).pack(side="left")
        self._dv = vsentry(row, 300, "радли, редли, radley")
        self._dv.pack(side="left", padx=(6, 12))

        self._dict_add_btn = vsbtn(row, "Добавить", self._dict_add, width=90,
                                   accent=True)
        self._dict_add_btn.pack(side="left")

        # Cancel edit button (hidden by default)
        self._dict_cancel_btn = vsbtn(row, "Отмена", self._dict_cancel_edit,
                                      width=80, danger=True)
        # Track which word is being edited
        self._editing_word: str | None = None

        lbl(page,
            "  // варианты через запятую — все способы написания этого слова",
            10, color=C["text_dim"]).pack(anchor="w", padx=12, pady=(6, 2))
        vsep(page).pack(fill="x")

        self._dict_list = ctk.CTkScrollableFrame(
            page, fg_color=C["bg"], corner_radius=0,
            scrollbar_button_color=C["input"],
            scrollbar_button_hover_color=C["active"])
        self._dict_list.pack(fill="both", expand=True)

        self._refresh_dict()

    def _refresh_dict(self):
        for w in self._dict_list.winfo_children():
            w.destroy()

        hdr = ctk.CTkFrame(self._dict_list, fg_color="transparent")
        hdr.pack(fill="x", padx=4, pady=(4, 0))
        lbl(hdr, "СЛОВО", 9, color=C["text_faint"], bold=True,
            width=160, anchor="w").pack(side="left")
        lbl(hdr, "ВАРИАНТЫ НАПИСАНИЯ", 9, color=C["text_faint"],
            bold=True, anchor="w").pack(side="left")
        vsep(self._dict_list).pack(fill="x", padx=4, pady=(4, 2))

        for correct, variants in dictionary.items():
            row = ctk.CTkFrame(self._dict_list, fg_color="transparent",
                               height=30, cursor="hand2")
            row.pack(fill="x", padx=4)
            row.pack_propagate(False)
            row.bind("<Enter>", lambda e, r=row: r.configure(fg_color=C["hover"]))
            row.bind("<Leave>", lambda e, r=row: r.configure(fg_color="transparent"))

            lbl(row, correct, 12, color=C["accent3"],
                width=160, anchor="w").pack(side="left", padx=(8, 0))
            lbl(row, "→", 11, color=C["text_faint"],
                width=20).pack(side="left")
            lbl(row, ", ".join(variants), 11, color=C["text"],
                anchor="w").pack(side="left", padx=(4, 0), fill="x", expand=True)

            x = ctk.CTkLabel(row, text="✕", width=28,
                              font=ctk.CTkFont("Consolas", 11),
                              text_color=C["text_faint"], cursor="hand2")
            x.pack(side="right", padx=6)
            x.bind("<Button-1>", lambda e, c=correct: self._dict_delete(c))
            x.bind("<Enter>", lambda e, w=x: w.configure(text_color=C["red"]))
            x.bind("<Leave>", lambda e, w=x: w.configure(text_color=C["text_faint"]))

            # Edit button
            ed = ctk.CTkLabel(row, text="✎", width=24,
                               font=ctk.CTkFont("Consolas", 13),
                               text_color=C["text_faint"], cursor="hand2")
            ed.pack(side="right", padx=(0, 2))
            ed.bind("<Button-1>", lambda e, c=correct, v=variants: self._dict_edit_fill(c, v))
            ed.bind("<Enter>", lambda e, w=ed: w.configure(text_color=C["accent"]))
            ed.bind("<Leave>", lambda e, w=ed: w.configure(text_color=C["text_faint"]))

            vsep(self._dict_list).pack(fill="x", padx=4)

    def _dict_edit_fill(self, word: str, variants: list):
        """Fill the form with existing word data for editing."""
        self._editing_word = word
        self._dw.delete(0, "end")
        self._dw.insert(0, word)
        self._dw.configure(state="disabled")  # Word key can't be changed during edit
        self._dv.delete(0, "end")
        self._dv.insert(0, ", ".join(variants))
        self._dict_add_btn.configure(text="Сохранить")
        self._dict_cancel_btn.pack(side="left", padx=(6, 0))

    def _dict_cancel_edit(self):
        """Cancel edit mode and reset form."""
        self._editing_word = None
        self._dw.configure(state="normal")
        self._dw.delete(0, "end")
        self._dv.delete(0, "end")
        self._dict_add_btn.configure(text="Добавить")
        self._dict_cancel_btn.pack_forget()

    def _dict_add(self):
        word     = self._dw.get().strip()
        variants = [v.strip() for v in self._dv.get().split(",") if v.strip()]
        if not word or not variants:
            return

        if self._editing_word is not None:
            # Update existing entry
            dictionary[self._editing_word] = variants
            save_dictionary(dictionary)
            self._append_log("sys", f"словарь: обновлено '{self._editing_word}' ({len(variants)} вариантов)")
            self._dict_cancel_edit()
        else:
            dictionary[word] = variants
            save_dictionary(dictionary)
            self._dw.delete(0, "end"); self._dv.delete(0, "end")
            self._append_log("sys", f"словарь: добавлено '{word}' ({len(variants)} вариантов)")
        self._refresh_dict()

    def _dict_delete(self, word: str):
        dictionary.pop(word, None)
        save_dictionary(dictionary)
        self._refresh_dict()

    # ══════════════════════════════════════════════════════════════════
    #  СТРАНИЦА: НАСТРОЙКИ
    # ══════════════════════════════════════════════════════════════════

    def _build_settings_page(self):
        page = ctk.CTkFrame(self.main, fg_color=C["bg"], corner_radius=0)
        self._pages["settings"] = page

        scroll = ctk.CTkScrollableFrame(
            page, fg_color=C["bg"], corner_radius=0,
            scrollbar_button_color=C["input"],
            scrollbar_button_hover_color=C["active"])
        scroll.pack(fill="both", expand=True)

        def section(title):
            f = ctk.CTkFrame(scroll, fg_color="transparent")
            f.pack(fill="x", padx=16, pady=(20, 6))
            lbl(f, f"// {title}", 10, color=C["text_dim"], bold=True).pack(side="left")
            vsep(scroll).pack(fill="x", padx=16, pady=(0, 4))

        def setting_row(label_text, widget_fn, hint=""):
            row = ctk.CTkFrame(scroll, fg_color="transparent", height=40)
            row.pack(fill="x", padx=16, pady=2)
            row.pack_propagate(False)
            lbl(row, label_text, 11, color=C["text"],
                width=200, anchor="w").pack(side="left")
            widget_fn(row)
            if hint:
                lbl(row, f"  // {hint}", 10,
                    color=C["text_faint"]).pack(side="left", padx=12)

        # ── Запись ──
        section("Запись")

        self._s_hotkey = ctk.StringVar(value=self.settings["hotkey"])
        def hotkey_w(r): vsentry(r, 160, textvariable=self._s_hotkey).pack(side="left")
        setting_row("Горячая клавиша", hotkey_w, "win+ctrl / alt+r / ...")

        self._s_min_dur = ctk.DoubleVar(value=self.settings["min_dur"])
        def mindur_w(r):
            sl = ctk.CTkSlider(r, from_=0.1, to=3.0, number_of_steps=29,
                                variable=self._s_min_dur, width=160,
                                button_color=C["accent"],
                                button_hover_color="#0090ef",
                                progress_color="#1a5a8a",
                                fg_color=C["input"])
            sl.pack(side="left")
            v = lbl(r, f"{self.settings['min_dur']:.1f}s", 11,
                     color=C["accent3"], width=36)
            v.pack(side="left", padx=8)
            sl.configure(command=lambda x, vl=v: vl.configure(text=f"{x:.1f}s"))
        setting_row("Мин. длина записи", mindur_w)

        # ── Распознавание ──
        section("Распознавание")

        self._s_lang = ctk.StringVar(value=self.settings["language"])
        def lang_w(r):
            vsoption(r, self._s_lang, ["auto", "keyboard_layout", "ru", "uk", "de", "en"]).pack(side="left")
        setting_row("Язык", lang_w, "auto = определять автоматически")

        self._s_beam = ctk.IntVar(value=self.settings["beam_size"])
        def beam_w(r):
            sl = ctk.CTkSlider(r, from_=1, to=10, number_of_steps=9,
                                variable=self._s_beam, width=160,
                                button_color=C["accent"],
                                button_hover_color="#0090ef",
                                progress_color="#1a5a8a",
                                fg_color=C["input"])
            sl.pack(side="left")
            v = lbl(r, str(self.settings["beam_size"]), 11,
                     color=C["accent3"], width=24)
            v.pack(side="left", padx=8)
            sl.configure(command=lambda x, vl=v: vl.configure(text=str(int(x))))
        setting_row("Beam size", beam_w, "выше = точнее, но медленнее")

        # ── Модель ──
        section("Модель")

        self._s_whisper_model = ctk.StringVar(value=self.settings.get("whisper_model", "turbo"))
        def whisper_model_w(r):
            vsoption(r, self._s_whisper_model,
                     ["tiny", "base", "small", "medium", "large-v2", "large-v3", "turbo"],
                     width=160).pack(side="left")
        setting_row("Whisper модель", whisper_model_w,
                    "turbo = быстро и точно / large-v3 = максимум точности")

        self._s_device = ctk.StringVar(value=self.settings["device"])
        def device_w(r):
            vsoption(r, self._s_device, ["cuda", "cpu"]).pack(side="left")
        setting_row("Устройство", device_w)

        self._s_compute = ctk.StringVar(value=self.settings["compute"])
        def compute_w(r):
            vsoption(r, self._s_compute,
                     ["float16", "int8", "float32"]).pack(side="left")
        setting_row("Тип вычислений", compute_w, "float16 = быстро (GPU)")

        # ── Кнопка ──
        vsep(scroll).pack(fill="x", padx=16, pady=(20, 0))
        bot = ctk.CTkFrame(scroll, fg_color="transparent")
        bot.pack(padx=16, pady=12, anchor="w")
        vsbtn(bot, "Сохранить", self._apply_settings,
              width=120, accent=True).pack(side="left")
        self._saved_lbl = lbl(bot, "", 10, color=C["green"])
        self._saved_lbl.pack(side="left", padx=12)

    def _apply_settings(self):
        reload = (self._s_device.get()  != self.settings["device"] or
                  self._s_compute.get() != self.settings["compute"] or
                  self._s_whisper_model.get() != self.settings.get("whisper_model", "turbo"))
        new_hk = self._s_hotkey.get().strip()
        self.settings.update({
            "hotkey":        new_hk,
            "language":      self._s_lang.get(),
            "beam_size":     int(self._s_beam.get()),
            "min_dur":       round(self._s_min_dur.get(), 1),
            "device":        self._s_device.get(),
            "compute":       self._s_compute.get(),
            "whisper_model": self._s_whisper_model.get(),
        })
        self._save_settings()
        self._register_hotkey(new_hk)
        self._hk_lbl.configure(text=new_hk.upper())
        self._sb_right.configure(
            text=f"{self.settings['device'].upper()} · {self.settings['compute']}  ")
        if reload:
            self._load_model_async()
        self._saved_lbl.configure(text="✓ сохранено")
        self.after(2000, lambda: self._saved_lbl.configure(text=""))

    # ══════════════════════════════════════════════════════════════════
    #  НАВИГАЦИЯ
    # ══════════════════════════════════════════════════════════════════

    def _switch_tab(self, key: str):
        self._current_tab = key
        for k, page in self._pages.items():
            page.pack_forget()
        self._pages[key].pack(fill="both", expand=True)

        titles = {"log": "ЛОГ", "dict": "СЛОВАРЬ", "settings": "НАСТРОЙКИ"}
        self._sidebar_title.configure(text=titles[key])

        for k, lb in self._act_btns.items():
            lb.configure(text_color=C["text"] if k == key else C["text_faint"])

        if key == "log":
            self._stat_frame.pack(fill="x", padx=8, pady=(0, 8))
        else:
            self._stat_frame.pack_forget()

    # ══════════════════════════════════════════════════════════════════
    #  АНИМАЦИЯ
    # ══════════════════════════════════════════════════════════════════

    def _animate(self):
        if self.recording:
            self._phase += 0.15
            t   = (math.sin(self._phase) + 1) / 2
            r_v = int(0   + 212 * t)
            g_v = int(122 + 100 * t)
            b_v = int(204 + 51  * t)
            col = f"#{r_v:02x}{g_v:02x}{b_v:02x}"
            self._rec_lbl.configure(text="● запись", text_color=col)
        else:
            self._rec_lbl.configure(text="● ожидание",
                                     text_color=C["text_faint"])
        self.after(40, self._animate)

    # ══════════════════════════════════════════════════════════════════
    #  МОДЕЛЬ
    # ══════════════════════════════════════════════════════════════════

    def _load_model_async(self):
        self.model = None
        self._model_lbl.configure(text="⟳ загрузка...", text_color=C["yellow"])
        threading.Thread(target=self._load_model_thread, daemon=True).start()

    def _load_model_thread(self):
        try:
            from faster_whisper import WhisperModel
            model_name = self.settings.get("whisper_model", "turbo")
            m = WhisperModel(model_name,
                             device=self.settings["device"],
                             compute_type=self.settings["compute"])
            self.model = m
            self.after(0, lambda: self._model_lbl.configure(
                text="✓ модель готова", text_color=C["green"]))
            self.after(0, lambda mn=model_name: self._append_log(
                "sys", f"модель загружена  [{mn} / {self.settings['device']} / "
                       f"{self.settings['compute']}]"))
        except Exception as e:
            self.after(0, lambda: self._model_lbl.configure(
                text="✗ ошибка", text_color=C["red"]))
            self.after(0, lambda: self._append_log("ERR", str(e)))

    # ══════════════════════════════════════════════════════════════════
    #  ХОТКЕЙ
    # ══════════════════════════════════════════════════════════════════

    def _register_hotkey(self, hotkey: str = None):
        if hotkey is None:
            hotkey = self.settings["hotkey"]
        try:
            if self.hotkey_ref:
                keyboard.remove_hotkey(self.hotkey_ref)
        except Exception:
            pass
        try:
            self.hotkey_ref = keyboard.add_hotkey(
                hotkey,
                lambda: threading.Thread(
                    target=self._record_and_transcribe, daemon=True).start(),
                trigger_on_release=False)
        except Exception as e:
            self.after(0, lambda: self._append_log("ERR", f"хоткей: {e}"))

    # ══════════════════════════════════════════════════════════════════
    #  МИКРОФОН — ВЫБОР УСТРОЙСТВА, МОНИТОРИНГ, ГРОМКОСТЬ
    # ══════════════════════════════════════════════════════════════════

    def _get_input_devices(self) -> list[tuple[int, str]]:
        """Return list of (index, name) for all input devices."""
        p = pyaudio.PyAudio()
        devices = []
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                devices.append((i, info["name"]))
        p.terminate()
        return devices

    def _refresh_mic_list(self):
        devices = self._get_input_devices()
        names = ["По умолчанию"] + [f"{i}: {n}" for i, n in devices]
        self._mic_combo.configure(values=names)
        saved_idx = self.settings.get("mic_device_index")
        if saved_idx is not None:
            for i, n in devices:
                if i == saved_idx:
                    self._mic_var.set(f"{i}: {n}")
                    self._mic_device_index = saved_idx
                    break

    def _on_mic_selected(self, choice: str):
        if choice == "По умолчанию":
            self._mic_device_index = None
            self.settings["mic_device_index"] = None
        else:
            idx = int(choice.split(":")[0])
            self._mic_device_index = idx
            self.settings["mic_device_index"] = idx
        self._save_settings()
        self._restart_mic_monitor()

    def _start_mic_monitor(self):
        self._mic_monitor_running = True
        self._mic_monitor_thread = threading.Thread(
            target=self._mic_monitor_loop, daemon=True)
        self._mic_monitor_thread.start()
        self._update_mic_bar()

    def _restart_mic_monitor(self):
        self._mic_monitor_running = False
        time.sleep(0.05)
        self._mic_monitor_running = True
        self._mic_monitor_thread = threading.Thread(
            target=self._mic_monitor_loop, daemon=True)
        self._mic_monitor_thread.start()

    def _mic_monitor_loop(self):
        CHUNK = 1024
        p = pyaudio.PyAudio()
        try:
            kw = {}
            if self._mic_device_index is not None:
                kw["input_device_index"] = self._mic_device_index
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                            input=True, frames_per_buffer=CHUNK, **kw)
            while self._mic_monitor_running:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    samples = [int.from_bytes(data[i:i+2], "little", signed=True)
                               for i in range(0, len(data), 2)]
                    rms = math.sqrt(sum(s*s for s in samples) / len(samples)) if samples else 0
                    # Convert to 0..1 log scale (silence ≈ 0, loud ≈ 1)
                    if rms > 0:
                        db = 20 * math.log10(rms / 32768)  # dB relative to full scale
                        db = max(db, -60)
                        level = (db + 60) / 60  # -60dB→0, 0dB→1
                    else:
                        db = -60
                        level = 0.0
                    self._mic_level = level
                    self._mic_db = db
                except Exception:
                    self._mic_level = 0.0
                    self._mic_db = -60
            stream.stop_stream()
            stream.close()
        except Exception:
            self._mic_level = 0.0
            self._mic_db = -60
        finally:
            p.terminate()

    def _update_mic_bar(self):
        if not self._tray_running:
            return
        self._redraw_mic_bar()
        try:
            db = getattr(self, "_mic_db", -60)
            self._mic_db_lbl.configure(text=f"{db:.1f} dB")
        except Exception:
            pass
        self.after(60, self._update_mic_bar)

    def _redraw_mic_bar(self, event=None):
        try:
            c = self._mic_bar_canvas
            w = c.winfo_width()
            h = c.winfo_height()
            if w < 2:
                return
            c.delete("all")
            level = getattr(self, "_mic_level", 0.0)
            # Background track
            c.create_rectangle(0, 0, w, h, fill=C["input"], outline="")
            # Coloured fill — green→yellow→red
            fill_w = int(w * min(level, 1.0))
            if fill_w > 0:
                if level < 0.5:
                    col = C["green"]
                elif level < 0.8:
                    col = C["yellow"]
                else:
                    col = C["red"]
                c.create_rectangle(0, 0, fill_w, h, fill=col, outline="")
            # Peak marker
            peak = getattr(self, "_mic_peak", 0.0)
            # Decay peak
            self._mic_peak = max(level, getattr(self, "_mic_peak", 0.0) * 0.95)
            px = int(w * min(self._mic_peak, 1.0))
            if px > 2:
                c.create_rectangle(px-2, 0, px, h, fill="white", outline="")
        except Exception:
            pass

    def _load_mic_volume(self):
        """Load current system mic volume (Windows)."""
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetMicrophone()
            interface = devices.Activate(IAudioEndpointVolume._iid_,
                                          CLSCTX_ALL, None)
            self._audio_endpoint = cast(interface, POINTER(IAudioEndpointVolume))
            vol = self._audio_endpoint.GetMasterVolumeLevelScalar()
            pct = round(vol * 100)
            self._mic_vol_var.set(pct)
            self._mic_vol_lbl.configure(text=f"{pct}%")
        except Exception:
            self._audio_endpoint = None

    def _on_mic_vol_change(self, val):
        pct = int(float(val))
        self._mic_vol_lbl.configure(text=f"{pct}%")
        try:
            if self._audio_endpoint:
                self._audio_endpoint.SetMasterVolumeLevelScalar(pct / 100.0, None)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════
    #  ЗАПИСЬ И ТРАНСКРИБАЦИЯ
    # ══════════════════════════════════════════════════════════════════

    def _record_and_transcribe(self):
        if not self.model or self.recording:
            return

        CHUNK, FORMAT, CHANNELS, RATE = 1024, pyaudio.paInt16, 1, 16000
        p            = pyaudio.PyAudio()
        sample_width = p.get_sample_size(FORMAT)
        open_kw = {}
        if self._mic_device_index is not None:
            open_kw["input_device_index"] = self._mic_device_index
        stream       = p.open(format=FORMAT, channels=CHANNELS,
                               rate=RATE, input=True, frames_per_buffer=CHUNK,
                               **open_kw)
        frames     = []
        start_time = time.time()

        self.recording = True
        self._tray_rec = True

        keys = [k.strip() for k in
                self.settings["hotkey"].replace("+", " ").split()]
        while all(keyboard.is_pressed(k) for k in keys):
            frames.append(stream.read(CHUNK, exception_on_overflow=False))

        self.recording = False
        self._tray_rec = False

        stream.stop_stream(); stream.close(); p.terminate()

        if time.time() - start_time < self.settings["min_dur"]:
            return

        audio_data = io.BytesIO()
        with wave.open(audio_data, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(sample_width)
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
        audio_data.seek(0)

        ALLOWED_LANGS = ["ru", "uk", "de", "en"]
        try:
            # ── Шаг 1: определяем язык ───────────────────────────────
            cur_setting = self.settings["language"]

            if cur_setting == "keyboard_layout":
                # По раскладке Windows
                layout_lang = get_keyboard_layout_lang()
                if layout_lang:
                    lang_opt = layout_lang
                    self.after(0, lambda l=lang_opt:
                               self._append_log("sys", f"раскладка → {l.upper()}"))
                else:
                    # Раскладка не распознана — fallback на auto
                    lang_opt = None
                    self.after(0, lambda:
                               self._append_log("sys", "раскладка не распознана, авто"))

            elif cur_setting == "auto":
                # Whisper сам определяет среди 4 языков
                import numpy as np
                import soundfile as sf
                audio_data.seek(0)
                audio_np, _ = sf.read(audio_data)
                if audio_np.ndim > 1:
                    audio_np = audio_np.mean(axis=1)
                audio_np = audio_np.astype(np.float32)

                result = self.model.detect_language(audio_np)
                lang_probs = result[2]
                best_lang = max(
                    ALLOWED_LANGS,
                    key=lambda l: next((p for ll, p in lang_probs if ll == l), 0.0)
                )
                detected_prob = next((p for ll, p in lang_probs if ll == best_lang), 0.0)
                self.after(0, lambda l=best_lang, p=detected_prob:
                           self._append_log("sys", f"авто → {l.upper()} ({p:.0%})"))
                audio_data.seek(0)
                lang_opt = best_lang

            else:
                lang_opt = cur_setting

            # ── Шаг 2: транскрибируем с известным языком ─────────────
            segments, info = self.model.transcribe(
                audio_data,
                beam_size=max(self.settings["beam_size"], 7),
                language=lang_opt,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=300,
                    speech_pad_ms=200,
                    threshold=0.4,
                ),
                no_speech_threshold=0.6,
                compression_ratio_threshold=2.0,
                temperature=[0.0, 0.2, 0.4],
                repetition_penalty=1.3,
                no_repeat_ngram_size=3,
            )
            text = "".join([s.text for s in segments]).strip()
            # Убираем лишнюю точку в конце (артефакт Whisper)
            if text.endswith(".") and not text.endswith("..."):
                text = text[:-1].rstrip()
            text = apply_dictionary(text)

            if text:
                self.after(0, lambda t=text, l=lang_opt: self._append_log(l, t))
                old = pyperclip.paste()
                pyperclip.copy(text)
                keyboard.send('ctrl+v')
                time.sleep(0.1)
                pyperclip.copy(old)
        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda m=err_msg: self._append_log("ERR", m))

    # ══════════════════════════════════════════════════════════════════
    #  ТРЕЙ
    # ══════════════════════════════════════════════════════════════════

    def _set_lang_from_tray(self, code: str):
        self.settings["language"] = code
        self._save_settings()
        # Синхронизируем настройки в UI если открыто
        try:
            self._s_lang.set(code)
        except Exception:
            pass
        labels = {"auto": "АВТО", "keyboard_layout": "⌨ РАСКЛАДКА", "ru": "RU", "uk": "UK", "de": "DE", "en": "EN"}
        self.after(0, lambda: self._append_log(
            "sys", f"язык: {labels.get(code, code)}"))
        try:
            self.after(0, self._build_lang_buttons)
        except Exception:
            pass

    def _tray_thread(self):
        threading.Thread(target=self._tray_icon.run, daemon=True).start()
        phase = 0.0
        while self._tray_running:
            if self._tray_rec:
                phase += 0.22
                self._tray_icon.icon  = make_tray_icon(phase, True)
                self._tray_icon.title = "Whisper — запись..."
            else:
                self._tray_icon.icon  = make_tray_icon(0, False)
                self._tray_icon.title = "Whisper Voice"
            time.sleep(0.03)

    def _show_from_tray(self):
        self.after(0, self.deiconify)
        self.after(0, self.lift)

    def _on_close(self):
        self.withdraw()

    def _quit_app(self):
        self._tray_running = False
        self._mic_monitor_running = False
        try: self._tray_icon.stop()
        except Exception: pass
        self.after(0, self.destroy)
        sys.exit(0)


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = WhisperApp()
    app.mainloop()