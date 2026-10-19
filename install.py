#!/usr/bin/env python3
"""Установщик тёмной графитовой темы «GNOME Graphite» для far2l.

Единственный источник правды по цветам — константы ниже. Всё остальное
(файл темы, палитра, настройки Colorer, иконки) генерируется или копируется отсюда.

Команды:
  python3 install.py                  установить тему (с резервной копией настроек)
  python3 install.py --verify         проверить, что всё установлено
  python3 install.py --restore FILE   откатиться из резервной копии
  python3 install.py --export DIR     сгенерировать готовые файлы темы (каталог theme/)

Перед установкой far2l должен быть закрыт: при выходе он сохраняет настройки
и перезаписал бы сделанные изменения.
"""
import argparse
import datetime
import glob
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
THEME_NAME = "GNOME Graphite"
HRD_NAME = "graphite"
MARKER = "# installed by far2l-dark-theme"
BACKUP_MANIFEST = "_far2l_dark_theme_backup.json"
# id .desktop-файла -> (имя иконки, файл в icons/)
DESKTOP_ICONS = {
    "far2l.desktop": ("far2l-graphite", "far2l-graphite.svg"),
    "far2ledit.desktop": ("far2ledit-graphite", "far2ledit-graphite.svg"),
}

# --- Цвета (палитра GNOME / libadwaita dark) -------------------------------------------
BG = "#1d1d20"        # основной фон: панели, редактор, просмотрщик, командная строка
SURF = "#2e2e32"      # «шапки»: верхнее меню, строки статуса, подписи F-клавиш, часы
DLG = "#36363a"       # диалоги, меню, справка
EDIT = "#4a4a4e"      # поля ввода в диалогах
EDIT_DIS = "#3f3f43"  # неактивные поля ввода
ACC_BG = "#1c71d8"    # акцент (синий GNOME): выбранный пункт меню/кнопка, активная панель
ACC_FG = "#78aeed"    # акцентный текст: горячие клавиши, заголовки колонок, ссылки
CURSOR = "#254165"    # курсор в панелях и выделение в редакторе (акцент 35% на фоне)
TEXT = "#deddda"      # обычный текст
BRIGHT = "#ffffff"    # яркий текст
SOFT = "#c0bfbc"      # чуть приглушённый текст
DIM = "#9a9996"       # вторичный текст
DIS = "#77767b"       # неактивный текст, рамки диалогов
LINE = "#55555c"      # рамки и полосы прокрутки панелей
LINENO = "#5e5c64"    # номера строк в редакторе
YEL = "#f8e45c"       # отмеченные файлы
YEL_HI = "#f9f06b"    # горячие клавиши на синем фоне
WARN = "#a51d2d"      # диалоги-предупреждения

# Базовая 16-цветная палитра (порядок индексов как в Windows-консоли).
# Через неё рисуются цвета типов файлов и вывод команд во встроенном терминале.
PALETTE_FG = ["#1d1d20", "#62a0ea", "#2ec27e", "#2aa1b3", "#e01b24", "#c061cb", "#e5a50a", "#deddda",
              "#8b8a90", "#99c1f1", "#8ff0a4", "#33c7de", "#f66151", "#dc8add", "#f8e45c", "#ffffff"]
PALETTE_BG = ["#1d1d20", "#1a5fb4", "#26a269", "#2aa1b3", "#c01c28", "#813d9c", "#a2734c", "#c0bfbc",
              "#5e5c64", "#3584e4", "#33d17a", "#33c7de", "#f66151", "#c061cb", "#f6d32d", "#ffffff"]

NAMES = ["BLACK", "BLUE", "GREEN", "CYAN", "RED", "MAGENTA", "BROWN", "LIGHTGRAY",
         "DARKGRAY", "LIGHTBLUE", "LIGHTGREEN", "LIGHTCYAN", "LIGHTRED", "LIGHTMAGENTA", "YELLOW", "WHITE"]

DIALOG = dict(bg=DLG, text=TEXT, hi=ACC_FG, box=DIS, title=BRIGHT, disabled=DIS,
              edit_bg=EDIT, edit_fg=BRIGHT, edit_unch=SOFT, edit_dis_bg=EDIT_DIS,
              sel_bg=ACC_BG, sel_fg=BRIGHT, sel_hi=YEL_HI, combo_bg=SURF, gray=DIM, sel_gray=TEXT)
WARNDIALOG = dict(bg=WARN, text=BRIGHT, hi=YEL_HI, box="#e8a0a6", title=BRIGHT, disabled="#d98d95",
                  edit_bg="#6e1420", edit_fg=BRIGHT, edit_unch="#f0c8cc", edit_dis_bg="#7f1a26",
                  sel_bg="#f6f5f4", sel_fg=BG, sel_hi=WARN, combo_bg="#6e1420", gray="#e8a0a6", sel_gray=LINENO)

FIXED = {
    "Panel.Text": (BG, TEXT),
    "Panel.Text.Selected": (BG, YEL),
    "Panel.Text.Highlight": (BG, SOFT),
    "Panel.Text.Info": (BG, ACC_FG),
    "Panel.Cursor": (CURSOR, BRIGHT),
    "Panel.Cursor.Selected": (CURSOR, YEL),
    "Panel.Title": (BG, DIM),
    "Panel.Title.Selected": (ACC_BG, BRIGHT),
    "Panel.Title.Column": (BG, ACC_FG),
    "Panel.Info.Total": (BG, DIM),
    "Panel.Info.Selected": (SURF, YEL),
    "Panel.DragText": (ACC_BG, BRIGHT),
    "Panel.Scrollbar": (BG, LINE),
    "Panel.Box": (BG, LINE),
    "Panel.ScreensNumber": (BG, ACC_FG),
    "HMenu.Text": (SURF, TEXT),
    "HMenu.Text.Selected": (ACC_BG, BRIGHT),
    "HMenu.Highlight": (SURF, ACC_FG),
    "HMenu.Highlight.Selected": (ACC_BG, YEL_HI),
    "Menu.Text": (DLG, TEXT),
    "Menu.Text.Selected": (ACC_BG, BRIGHT),
    "Menu.Text.Disabled": (DLG, DIS),
    "Menu.Highlight": (DLG, ACC_FG),
    "Menu.Highlight.Selected": (ACC_BG, YEL_HI),
    "Menu.Box": (DLG, DIS),
    "Menu.Title": (DLG, BRIGHT),
    "Menu.Scrollbar": (DLG, DIS),
    "Menu.Arrows": (DLG, ACC_FG),
    "Menu.Arrows.Disabled": (DLG, DIS),
    "Menu.Arrows.Selected": (ACC_BG, YEL_HI),
    "Menu.GrayText": (DLG, DIM),
    "Menu.GrayText.Selected": (ACC_BG, TEXT),
    "Menu.Prefix": (DLG, DIM),
    "Menu.Prefix.Selected": (ACC_BG, TEXT),
    "Keybar.Num": (BG, DIM),
    "Keybar.Text": (SURF, TEXT),
    "Keybar.Background": (BG, DIM),
    "CommandLine": (BG, TEXT),
    "CommandLine.Prefix": (BG, ACC_FG),
    "CommandLine.Selected": (ACC_BG, BRIGHT),
    "CommandLine.UserScreen": (BG, TEXT),
    "Clock": (SURF, TEXT),
    "Editor.Clock": (SURF, TEXT),
    "Viewer.Clock": (SURF, TEXT),
    "Viewer.Text": (BG, TEXT),
    "Viewer.Text.Selected": (ACC_BG, BRIGHT),
    "Viewer.Status": (SURF, TEXT),
    "Viewer.Arrows": (BG, ACC_FG),
    "Viewer.Scrollbar": (BG, LINE),
    "Editor.Text": (BG, TEXT),
    "Editor.Text.Selected": (CURSOR, BRIGHT),
    "Editor.Status": (SURF, TEXT),
    "Editor.LineNumber": (BG, LINENO),
    "Editor.Scrollbar": (BG, LINE),
    "Help.Text": (DLG, TEXT),
    "Help.Text.Highlight": (DLG, BRIGHT),
    "Help.Topic": (DLG, ACC_FG),
    "Help.Topic.Selected": (ACC_BG, BRIGHT),
    "Help.Box": (DLG, DIS),
    "Help.Box.Title": (DLG, BRIGHT),
    "Help.Scrollbar": (DLG, DIS),
    "Not.Used": (BG, DIS),
}

# Семейства для ключей, которых нет в правилах (могут появиться в новых версиях far2l):
# фон, текст, акцент, рамка, неактивный, фон выбранного, текст выбранного.
FAMILIES = {
    "Panel": (BG, TEXT, ACC_FG, LINE, DIS, CURSOR, BRIGHT),
    "Menu": (DLG, TEXT, ACC_FG, DIS, DIS, ACC_BG, BRIGHT),
    "HMenu": (SURF, TEXT, ACC_FG, DIS, DIS, ACC_BG, BRIGHT),
    "Help": (DLG, TEXT, ACC_FG, DIS, DIS, ACC_BG, BRIGHT),
    "Dialog": (DLG, TEXT, ACC_FG, DIS, DIS, ACC_BG, BRIGHT),
    "WarnDialog": (WARN, BRIGHT, YEL_HI, "#e8a0a6", "#d98d95", "#f6f5f4", BG),
}
DEFAULT_FAMILY = (BG, TEXT, ACC_FG, LINE, DIS, ACC_BG, BRIGHT)


def dialog_color(suffix, s):
    simple = {
        "Text": (s["bg"], s["text"]),
        "Text.Highlight": (s["bg"], s["hi"]),
        "Box": (s["bg"], s["box"]),
        "Box.Title": (s["bg"], s["title"]),
        "Box.Title.Highlight": (s["bg"], s["hi"]),
        "Button": (s["bg"], s["text"]),
        "Button.Highlight": (s["bg"], s["hi"]),
        "Button.Selected": (s["sel_bg"], s["sel_fg"]),
        "Button.Highlight.Selected": (s["sel_bg"], s["sel_hi"]),
        "DefaultButton": (s["bg"], s["title"]),
        "DefaultButton.Highlight": (s["bg"], s["hi"]),
        "DefaultButton.Selected": (s["sel_bg"], s["sel_fg"]),
        "DefaultButton.Highlight.Selected": (s["sel_bg"], s["sel_hi"]),
        "Disabled": (s["bg"], s["disabled"]),
        "Edit": (s["edit_bg"], s["edit_fg"]),
        "Edit.Selected": (s["sel_bg"], s["sel_fg"]),
        "Edit.Unchanged": (s["edit_bg"], s["edit_unch"]),
        "Edit.Disabled": (s["edit_dis_bg"], s["disabled"]),
        "OverflowArrow": (s["edit_bg"], s["hi"]),
    }
    if suffix in simple:
        return simple[suffix]
    m = re.fullmatch(r"(List|Combo)(?:\.(.+))?", suffix)
    if not m:
        return None
    lbg = s["bg"] if m.group(1) == "List" else s["combo_bg"]
    menu = {
        "": (lbg, s["text"]),
        "Text": (lbg, s["text"]),
        "Text.Selected": (s["sel_bg"], s["sel_fg"]),
        "Selected": (s["sel_bg"], s["sel_gray"]),
        "Highlight": (lbg, s["hi"]),
        "Highlight.Selected": (s["sel_bg"], s["sel_hi"]),
        "Box": (lbg, s["box"]),
        "Title": (lbg, s["title"]),
        "Scrollbar": (lbg, s["box"]),
        "Arrows": (lbg, s["hi"]),
        "Arrows.Disabled": (lbg, s["disabled"]),
        "Arrows.Selected": (s["sel_bg"], s["sel_hi"]),
        "Disabled": (lbg, s["disabled"]),
        "GrayText": (lbg, s["gray"]),
        "GrayText.Selected": (s["sel_bg"], s["sel_gray"]),
    }
    return menu.get(m.group(2) or "")


def guess_color(key):
    """Цвет для ключа без явного правила — по семейству и словам в имени."""
    bg, text, hi, box, disabled, sel_bg, sel_fg = FAMILIES.get(key.split(".")[0], DEFAULT_FAMILY)
    words = key.split(".")[1:]
    if "Selected" in words:
        return sel_bg, sel_fg
    if "Highlight" in words or "Arrows" in words:
        return bg, hi
    if "Disabled" in words or "GrayText" in words:
        return bg, disabled
    if "Box" in words or "Scrollbar" in words:
        return bg, box
    return bg, text


def color_for(key):
    """(фон, текст, есть_ли_явное_правило)."""
    if key in FIXED:
        return FIXED[key] + (True,)
    for prefix, scheme in (("Dialog.", DIALOG), ("WarnDialog.", WARNDIALOG)):
        if key.startswith(prefix):
            c = dialog_color(key[len(prefix):], scheme)
            if c:
                return c + (True,)
    return guess_color(key) + (False,)


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def nearest(h, palette):
    c = rgb(h)
    return min(range(16), key=lambda i: sum((a - b) ** 2 for a, b in zip(c, rgb(palette[i]))))


def expr(bg, fg):
    """Строка цвета в том же формате, в каком far2l сам сохраняет farcolors.ini.
    far2l читает её до «;»: RGB-цвета плюс запасные 16-цветные индексы."""
    b, f = rgb(bg), rgb(fg)
    return (f"background:{bg.lower()} foreground:{fg.lower()}, "
            f"B_{NAMES[nearest(bg, PALETTE_BG)]} | F_{NAMES[nearest(fg, PALETTE_FG)]}; "
            f"back_rgb({b[0]}, {b[1]}, {b[2]}) | fore_rgb({f[0]}, {f[1]}, {f[2]})")


# --- ini-файлы far2l ------------------------------------------------------------------------

class Ini:
    """Точечное редактирование ini far2l без переформатирования остального файла."""

    def __init__(self, path):
        self.path = path
        self.lines = []
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="surrogateescape") as fh:
                self.lines = fh.read().split("\n")

    def _bounds(self, section):
        header = f"[{section}]"
        for i, line in enumerate(self.lines):
            if line.strip() == header:
                end = next((j for j in range(i + 1, len(self.lines))
                            if self.lines[j].lstrip().startswith("[")), len(self.lines))
                return i, end
        return None

    def sections(self):
        return [s.strip()[1:-1] for s in self.lines if s.strip().startswith("[") and s.strip().endswith("]")]

    def items(self, section):
        b = self._bounds(section)
        out = {}
        if b:
            for line in self.lines[b[0] + 1:b[1]]:
                if "=" in line:
                    k, v = line.split("=", 1)
                    out.setdefault(k.strip(), v.strip())
        return out

    def set(self, section, values):
        b = self._bounds(section)
        if b is None:
            while self.lines and not self.lines[-1].strip():
                self.lines.pop()
            if self.lines:
                self.lines.append("")
            self.lines.append(f"[{section}]")
            self.lines += [f"{k}={v}" for k, v in values.items()]
            self.lines.append("")
            return
        start, end = b
        pending = dict(values)
        last = start
        for i in range(start + 1, end):
            if "=" in self.lines[i]:
                last = i
                k = self.lines[i].split("=", 1)[0].strip()
                if k in pending:
                    self.lines[i] = f"{k}={pending.pop(k)}"
        for j, (k, v) in enumerate(pending.items()):
            self.lines.insert(last + 1 + j, f"{k}={v}")

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write("\n".join(self.lines))


# --- где что лежит ---------------------------------------------------------------------------

def default_config_dir():
    """Повторяет логику far2l (utils/src/InMy.cpp): FARSETTINGS, XDG_CONFIG_HOME, ~/.config."""
    fs = os.environ.get("FARSETTINGS", "")
    while len(fs) > 1 and fs.endswith("/"):
        fs = fs[:-1]
    if fs.startswith("/"):
        return os.path.join(fs, ".config")
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = xdg if xdg.startswith("/") else os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, "far2l")
    return os.path.join(path, "custom", fs) if fs else path


def far2l_env_prefix(cfg):
    """Префикс команды, чтобы far2l запустился именно с этим каталогом настроек (или None)."""
    if os.path.realpath(cfg) == os.path.realpath(default_config_dir()):
        return ""
    if os.path.basename(cfg.rstrip("/")) == ".config":
        return "env FARSETTINGS=" + shlex.quote(os.path.dirname(os.path.abspath(cfg.rstrip("/")))) + " "
    return None


def system_theme_dirs():
    dirs = []
    exe = shutil.which("far2l")
    if exe:
        prefix = os.path.dirname(os.path.dirname(os.path.realpath(exe)))
        dirs.append(os.path.join(prefix, "share", "far2l", "themes"))
    dirs += ["/usr/share/far2l/themes", "/usr/local/share/far2l/themes"]
    seen, out = set(), []
    for d in dirs:
        r = os.path.realpath(d)
        if os.path.isdir(r) and r not in seen:
            seen.add(r)
            out.append(r)
    return out


def data_home():
    xdg = os.environ.get("XDG_DATA_HOME", "")
    return xdg if xdg.startswith("/") else os.path.expanduser("~/.local/share")


def data_dirs():
    return [d for d in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if d]


def color_keys(cfg):
    """Все известные имена цветов: из готового файла темы, тем, поставляемых с far2l
    (они сохранены этой же версией far2l), и текущих настроек пользователя."""
    keys = set(Ini(os.path.join(HERE, "theme", "farcolors.ini")).items("farcolors"))
    for d in system_theme_dirs():
        for f in glob.glob(os.path.join(d, "*", "farcolors.ini")):
            keys |= set(Ini(f).items("farcolors"))
    keys |= set(Ini(os.path.join(cfg, "settings", "farcolors.ini")).items("farcolors"))
    keys.discard("")
    # В некоторых штатных темах встречаются обрезанные имена (Panel.Info.Tota) — отбрасываем.
    truncated = {k for k in keys for o in keys if o != k and o.startswith(k) and o[len(k)] != "."}
    return sorted(keys - truncated)


def highlight_groups(ini):
    return [s for s in ini.sections() if re.fullmatch(r"Colors/Highlight/Group\d+", s)]


def far2l_running():
    try:
        return subprocess.run(["pgrep", "-x", "far2l"], stdout=subprocess.DEVNULL).returncode == 0
    except FileNotFoundError:
        return False


# --- шаги установки --------------------------------------------------------------------------

def theme_text(keys):
    lines = ["[farcolors]"]
    guessed = []
    for k in keys:
        bg, fg, exact = color_for(k)
        if not exact:
            guessed.append(k)
        lines.append(f"{k}={expr(bg, fg)}")
    return "\n".join(lines) + "\n", guessed


def palette_text():
    out = []
    for section, pal in (("foreground", PALETTE_FG), ("background", PALETTE_BG)):
        out.append(f"[{section}]")
        out += [f"{i}={pal[i].upper()}" for i in sorted(range(16), key=str)]
        out.append("")
    return "\n".join(out) + "\n"


def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def step_theme(cfg):
    keys = color_keys(cfg)
    text, guessed = theme_text(keys)
    tdir = os.path.join(cfg, "settings", "themes", THEME_NAME)
    write_file(os.path.join(tdir, "farcolors.ini"), text)
    write_file(os.path.join(tdir, "author.txt"),
               "Very dark graphite theme in GNOME / libadwaita dark colors.\n"
               "https://github.com/vabuter/far2l-dark-theme\n")
    ini = Ini(os.path.join(cfg, "settings", "colors.ini"))
    ini.set("Colors", {"CurrentTheme": THEME_NAME, "CurrentThemeIsSystemWide": "0"})
    ini.save()
    print(f"[ok] тема «{THEME_NAME}»: {len(keys)} цветов, выбрана текущей")
    if guessed:
        print(f"[!] нет явного правила для {len(guessed)} ключей, цвет подобран по названию: " + ", ".join(guessed))
    if not system_theme_dirs():
        # Старые сборки без поддержки тем читают только settings/farcolors.ini.
        write_file(os.path.join(cfg, "settings", "farcolors.ini"), text)
        print("[!] каталог тем far2l не найден (старая сборка?) — цвета записаны и в settings/farcolors.ini")


def step_palette(cfg):
    write_file(os.path.join(cfg, "palette.ini"), palette_text())
    print("[ok] базовая палитра 16 цветов: palette.ini")


def step_highlight(cfg):
    """Цвет файла под курсором = его обычный цвет: штатные значения рассчитаны
    на светло-бирюзовый курсор и на тёмном курсоре не читаются."""
    ini = Ini(os.path.join(cfg, "settings", "colors.ini"))
    groups = highlight_groups(ini)
    if not groups:
        print("[!] групп раскраски файлов нет (far2l ещё не запускался) — шаг пропущен")
        return False
    changed = 0
    for sec in groups:
        g = ini.items(sec)
        if g.get("CursorColor", "0x0") != "0x0" and g.get("NormalColor", "0x0") != "0x0":
            if g.get("CursorColor") != g["NormalColor"] or g.get("CursorColorMask") != g.get("NormalColorMask"):
                ini.set(sec, {"CursorColor": g["NormalColor"], "CursorColorMask": g.get("NormalColorMask", "0xfffffffd0f")})
                changed += 1
    ini.save()
    print(f"[ok] раскраска файлов: цвет под курсором выровнен ({changed} групп изменено из {len(groups)})")
    return True


def step_colorer(cfg):
    cdir = os.path.join(cfg, "plugins", "colorer")
    hrd = os.path.join(cdir, f"{HRD_NAME}.hrd")
    sets = os.path.join(cdir, "user-hrd.xml")
    os.makedirs(cdir, exist_ok=True)
    shutil.copyfile(os.path.join(HERE, "theme", f"{HRD_NAME}.hrd"), hrd)
    write_file(sets, '<?xml version="1.0" encoding="UTF-8"?>\n<hrd-sets>\n'
                     f'  <hrd class="rgb" name="{HRD_NAME}" description="GNOME Graphite">\n'
                     f'    <location link="{hrd}"/>\n'
                     '  </hrd>\n</hrd-sets>\n')
    ini = Ini(os.path.join(cdir, "config.ini"))
    ini.set("Settings", {"HrdNameTm": HRD_NAME, "HrdName": "black", "UserHrdPath": sets, "TrueMod": "1"})
    ini.save()
    print(f"[ok] подсветка синтаксиса Colorer: схема «{HRD_NAME}»")


def find_desktop(desktop_id, dhome):
    for d in [dhome] + data_dirs():
        p = os.path.join(d, "applications", desktop_id)
        if os.path.isfile(p):
            return p
    return None


def set_desktop_icon(text, icon):
    out, group, done = [], None, False
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            group = s
        elif group == "[Desktop Entry]" and s.startswith("Icon="):
            line, done = f"Icon={icon}", True
        out.append(line)
    if not done:
        i = next(n for n, l in enumerate(out) if l.strip() == "[Desktop Entry]")
        out.insert(i + 1, f"Icon={icon}")
    if MARKER not in out:
        out.insert(0, MARKER)
    return "\n".join(out)


def step_icons(dhome):
    if sys.platform == "darwin":
        print("[-] иконки: на macOS не ставятся (только Linux/XDG)")
        return
    idir = os.path.join(dhome, "icons", "hicolor", "scalable", "apps")
    adir = os.path.join(dhome, "applications")
    os.makedirs(idir, exist_ok=True)
    os.makedirs(adir, exist_ok=True)
    for desktop_id, (icon, svg) in DESKTOP_ICONS.items():
        shutil.copyfile(os.path.join(HERE, "icons", svg), os.path.join(idir, svg))
        src = find_desktop(desktop_id, dhome)
        if not src:
            print(f"[!] иконки: {desktop_id} не найден ни в одном каталоге applications — пропущен")
            continue
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
        write_file(os.path.join(adir, desktop_id), set_desktop_icon(text, icon))
        print(f"[ok] иконка {icon} -> {os.path.join(adir, desktop_id)}")
    os.utime(os.path.join(dhome, "icons", "hicolor"))
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", adir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def bootstrap(cfg, timeout=25):
    """Первый запуск far2l в tmux (TTY-режим) и выход, чтобы он создал штатные настройки."""
    prefix = far2l_env_prefix(cfg)
    if prefix is None or not shutil.which("tmux") or not shutil.which("far2l"):
        return False
    sock = f"far2l-theme-boot-{os.getpid()}"
    tmux = ["tmux", "-L", sock]
    empty = tempfile.mkdtemp(prefix="far2l-theme-boot-")
    cmd = f"cd {shlex.quote(empty)} && {prefix}TERM=xterm-256color far2l --tty --nodetect --mortal"
    print("[..] первый запуск far2l в tmux, чтобы он создал настройки по умолчанию")
    try:
        subprocess.run(tmux + ["-f", "/dev/null", "new-session", "-d", "-x", "120", "-y", "35", cmd], check=True)
        time.sleep(3)
        keys = ["Escape", "F10", "Enter"]
        deadline = time.time() + timeout
        while time.time() < deadline:
            if subprocess.run(tmux + ["has-session"], stderr=subprocess.DEVNULL).returncode != 0:
                break
            subprocess.run(tmux + ["send-keys", keys[0]], stderr=subprocess.DEVNULL)
            keys = keys[1:] + keys[:1]
            time.sleep(1.5)
    finally:
        subprocess.run(tmux + ["kill-server"], stderr=subprocess.DEVNULL)
        shutil.rmtree(empty, ignore_errors=True)
    return bool(highlight_groups(Ini(os.path.join(cfg, "settings", "colors.ini"))))


def backup(cfg, dhome):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = f"{cfg.rstrip('/')}-backup-{ts}.tar.gz"
    n = 1
    while os.path.exists(path):
        n += 1
        path = f"{cfg.rstrip('/')}-backup-{ts}-{n}.tar.gz"
    arc = os.path.basename(cfg.rstrip("/"))
    desktops, icons = [], []
    with tarfile.open(path, "w:gz") as tar:
        if os.path.isdir(cfg):
            tar.add(cfg, arcname=arc)
        for desktop_id, (icon, svg) in DESKTOP_ICONS.items():
            p = os.path.join(dhome, "applications", desktop_id)
            if os.path.isfile(p):
                tar.add(p, arcname=f"_desktop/{desktop_id}")
                desktops.append(desktop_id)
            p = os.path.join(dhome, "icons", "hicolor", "scalable", "apps", svg)
            if os.path.isfile(p):
                tar.add(p, arcname=f"_icons/{svg}")
                icons.append(svg)
        data = json.dumps({"config_dir": cfg, "arcname": arc, "config_existed": os.path.isdir(cfg),
                           "data_home": dhome, "desktop_files": desktops, "icon_files": icons},
                          ensure_ascii=False).encode()
        info = tarfile.TarInfo(BACKUP_MANIFEST)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    print(f"[ok] резервная копия: {path}")
    return path


def restore(path, dhome_override=None):
    with tarfile.open(path, "r:gz") as tar:
        meta = json.load(tar.extractfile(BACKUP_MANIFEST))
        cfg, arc = meta["config_dir"], meta["arcname"]
        dhome = dhome_override or meta["data_home"]
        if os.path.isdir(cfg):
            aside = f"{cfg.rstrip('/')}.replaced-{datetime.datetime.now():%Y%m%d-%H%M%S}"
            os.rename(cfg, aside)
            print(f"[ok] текущие настройки отложены в {aside}")
        parent = os.path.dirname(cfg.rstrip("/"))
        members = [m for m in tar.getmembers() if m.name == arc or m.name.startswith(arc + "/")]
        kwargs = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        if meta["config_existed"]:
            tar.extractall(parent, members=members, **kwargs)
            print(f"[ok] настройки восстановлены: {cfg}")
        for desktop_id, (icon, svg) in DESKTOP_ICONS.items():
            p = os.path.join(dhome, "applications", desktop_id)
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as fh:
                    ours = MARKER in fh.read()
                if ours:
                    os.remove(p)
            if desktop_id in meta["desktop_files"]:
                m = tar.getmember(f"_desktop/{desktop_id}")
                with open(p, "wb") as fh:
                    fh.write(tar.extractfile(m).read())
            svg_path = os.path.join(dhome, "icons", "hicolor", "scalable", "apps", svg)
            if os.path.isfile(svg_path):
                os.remove(svg_path)
            if svg in meta.get("icon_files", []):
                with open(svg_path, "wb") as fh:
                    fh.write(tar.extractfile(f"_icons/{svg}").read())
    print("[ok] иконки и .desktop-файлы — как на момент резервной копии")


# --- проверка --------------------------------------------------------------------------------

def verify(cfg, dhome, check_icons=True):
    results = []

    def check(ok, msg):
        results.append(ok)
        print(("[ok] " if ok else "[FAIL] ") + msg)

    check(os.path.isdir(cfg), f"каталог настроек: {cfg}")
    tfile = os.path.join(cfg, "settings", "themes", THEME_NAME, "farcolors.ini")
    installed = Ini(tfile).items("farcolors")
    missing = [k for k in color_keys(cfg) if k not in installed]
    check(bool(installed) and not missing,
          f"файл темы {tfile}" + (f" (нет ключей: {', '.join(missing)})" if missing else f" ({len(installed)} цветов)"))
    expected_theme, _ = theme_text(sorted(installed))
    check(Ini(tfile).lines == expected_theme.split("\n"), "цвета в файле темы совпадают с install.py")
    colors = Ini(os.path.join(cfg, "settings", "colors.ini"))
    cur = colors.items("Colors")
    check(cur.get("CurrentTheme") == THEME_NAME and cur.get("CurrentThemeIsSystemWide") == "0",
          f"текущая тема в colors.ini: «{cur.get('CurrentTheme', '')}»")
    pal = os.path.join(cfg, "palette.ini")
    check(os.path.isfile(pal) and open(pal, encoding="utf-8").read() == palette_text(), "palette.ini совпадает с install.py")
    groups = highlight_groups(colors)
    bad = [s for s in groups if colors.items(s).get("CursorColor", "0x0") not in ("0x0", colors.items(s).get("NormalColor"))]
    check(bool(groups) and not bad, f"раскраска файлов: {len(groups)} групп, расхождений под курсором: {len(bad)}")
    cc = Ini(os.path.join(cfg, "plugins", "colorer", "config.ini")).items("Settings")
    uh = cc.get("UserHrdPath", "")
    hrd_ok = os.path.isfile(uh) and os.path.isfile(os.path.join(cfg, "plugins", "colorer", f"{HRD_NAME}.hrd"))
    check(cc.get("HrdNameTm") == HRD_NAME and cc.get("TrueMod") == "1" and hrd_ok,
          f"Colorer: HrdNameTm={cc.get('HrdNameTm')}, TrueMod={cc.get('TrueMod')}, UserHrdPath={uh or '-'}")
    if check_icons and sys.platform != "darwin":
        for desktop_id, (icon, svg) in DESKTOP_ICONS.items():
            p = os.path.join(dhome, "applications", desktop_id)
            svg_ok = os.path.isfile(os.path.join(dhome, "icons", "hicolor", "scalable", "apps", svg))
            icon_line = ""
            if os.path.isfile(p):
                icon_line = next((l for l in open(p, encoding="utf-8").read().split("\n") if l.startswith("Icon=")), "")
            if not os.path.isfile(p) and not find_desktop(desktop_id, dhome):
                print(f"[-] {desktop_id}: в системе нет — иконка не нужна")
                continue
            check(svg_ok and icon_line == f"Icon={icon}", f"иконка {desktop_id}: {icon_line or 'нет переопределения'}")
    ok = all(results)
    print("ИТОГ: " + ("всё установлено" if ok else "есть проблемы (см. FAIL)"))
    return ok


# --- точка входа -----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Тёмная графитовая тема GNOME Graphite для far2l")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="проверить установку")
    mode.add_argument("--restore", metavar="BACKUP", help="откатиться из резервной копии .tar.gz")
    mode.add_argument("--export", metavar="DIR", help="записать готовые farcolors.ini и palette.ini в DIR")
    ap.add_argument("--config-dir", default=None, help="каталог настроек far2l (по умолчанию как у far2l)")
    ap.add_argument("--data-home", default=None, help="куда ставить иконки (по умолчанию $XDG_DATA_HOME или ~/.local/share)")
    ap.add_argument("--skip-icons", action="store_true", help="не трогать иконки")
    ap.add_argument("--skip-colorer", action="store_true", help="не трогать подсветку синтаксиса")
    ap.add_argument("--skip-palette", action="store_true", help="не трогать palette.ini")
    ap.add_argument("--skip-highlight", action="store_true", help="не трогать раскраску файлов")
    ap.add_argument("--no-bootstrap", action="store_true", help="не запускать far2l для создания настроек")
    ap.add_argument("--no-backup", action="store_true", help="не делать резервную копию")
    ap.add_argument("--force", action="store_true", help="продолжить, даже если far2l запущен")
    a = ap.parse_args()

    cfg = os.path.abspath(os.path.expanduser(a.config_dir)) if a.config_dir else default_config_dir()
    dhome = os.path.abspath(os.path.expanduser(a.data_home)) if a.data_home else data_home()

    if a.export:
        text, guessed = theme_text(color_keys(cfg))
        write_file(os.path.join(a.export, "farcolors.ini"), text)
        write_file(os.path.join(a.export, "palette.ini"), palette_text())
        print(f"[ok] записано в {a.export}" + (f"; подобрано по названию: {', '.join(guessed)}" if guessed else ""))
        return 0
    if a.verify:
        return 0 if verify(cfg, dhome, check_icons=not a.skip_icons) else 1

    if far2l_running() and not a.force:
        print("[STOP] far2l запущен. Закройте его (F10) и повторите: при выходе он перезапишет настройки.\n"
              "       Если запущенный far2l использует другой каталог настроек, добавьте --force.")
        return 2
    if a.restore:
        restore(a.restore, a.data_home and dhome)
        return 0

    print(f"Каталог настроек far2l: {cfg}")
    if not a.no_backup:
        backup(cfg, dhome)
    groups = highlight_groups(Ini(os.path.join(cfg, "settings", "colors.ini")))
    if not groups and not a.no_bootstrap and not a.skip_highlight:
        if bootstrap(cfg):
            print("[ok] far2l создал настройки по умолчанию")
        else:
            print("[!] не удалось автоматически создать настройки far2l (нужны tmux и far2l в PATH).\n"
                  "    Запустите far2l один раз, выйдите по F10 и повторите установку.")
    step_theme(cfg)
    if not a.skip_palette:
        step_palette(cfg)
    if not a.skip_highlight:
        step_highlight(cfg)
    if not a.skip_colorer:
        step_colorer(cfg)
    if not a.skip_icons:
        step_icons(dhome)
    print("Готово. Запустите far2l. Проверка: python3 install.py --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
