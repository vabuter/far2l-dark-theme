"""Цвета интерфейса и палитра темы «GNOME Graphite» для всех версий far2l.
(Цвета подсветки синтаксиса в редакторе — в theme/graphite.hrd; фон строк там равен BG.)

Отсюда генерируются:
  * файл цветов интерфейса (farcolors.ini) — для любого набора имён цветов;
  * базовая 16-цветная палитра (palette.ini).
"""
import re

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
LINE = "#55555c"      # рамки панелей
YEL = "#f8e45c"       # отмеченные файлы
YEL_HI = "#f9f06b"    # горячие клавиши на синем фоне
WARN = "#a51d2d"      # диалоги-предупреждения

# Сборки far2l новее 2.8.0 сами осветляют малоконтрастный текст (EnforceColorCorrection),
# а 2.6.x — нет. Чтобы тема везде выглядела одинаково, здесь сразу записаны значения,
# которые получаются после такой коррекции.
SCROLL = "#75757c"    # полосы прокрутки на основном фоне
LINENO = "#77757d"    # номера строк в редакторе
DIS_DLG = "#8a898e"   # неактивный текст и прокрутка на фоне диалогов и меню
DIS_SURF = "#838287"  # то же на фоне выпадающих списков
DIS_EDIT = "#8f8e93"  # то же в неактивных полях ввода

# Базовая 16-цветная палитра (порядок индексов как в Windows-консоли).
# Через неё рисуются цвета типов файлов и вывод команд во встроенном терминале.
# В терминальном режиме far2l отправляет терминалу одну палитру: цвета 0–7 из [background],
# 8–15 из [foreground]. Поэтому цвета 1–7 [background] подобраны так, чтобы читаться и как текст.
PALETTE_FG = ["#1d1d20", "#62a0ea", "#2ec27e", "#2aa1b3", "#e01b24", "#c061cb", "#e5a50a", "#deddda",
              "#8b8a90", "#99c1f1", "#8ff0a4", "#33c7de", "#f66151", "#dc8add", "#f8e45c", "#ffffff"]
PALETTE_BG = ["#1d1d20", "#1c71d8", "#26a269", "#2aa1b3", "#e01b24", "#a347ba", "#e5a50a", "#deddda",
              "#5e5c64", "#3584e4", "#33d17a", "#33c7de", "#f66151", "#c061cb", "#f6d32d", "#ffffff"]

NAMES = ["BLACK", "BLUE", "GREEN", "CYAN", "RED", "MAGENTA", "BROWN", "LIGHTGRAY",
         "DARKGRAY", "LIGHTBLUE", "LIGHTGREEN", "LIGHTCYAN", "LIGHTRED", "LIGHTMAGENTA", "YELLOW", "WHITE"]

DIALOG = dict(bg=DLG, text=TEXT, hi=ACC_FG, box=DIS, title=BRIGHT, disabled=DIS,
              edit_bg=EDIT, edit_fg=BRIGHT, edit_unch=SOFT, edit_dis_bg=EDIT_DIS,
              sel_bg=ACC_BG, sel_fg=BRIGHT, sel_hi=YEL_HI, combo_bg=SURF, gray=DIM, sel_gray=TEXT)
WARNDIALOG = dict(bg=WARN, text=BRIGHT, hi=YEL_HI, box="#e8a0a6", title=BRIGHT, disabled="#d98d95",
                  edit_bg="#6e1420", edit_fg=BRIGHT, edit_unch="#f0c8cc", edit_dis_bg="#7f1a26",
                  sel_bg="#f6f5f4", sel_fg=BG, sel_hi=WARN, combo_bg="#6e1420", gray="#e8a0a6", sel_gray="#5e5c64")

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
    "Panel.Info.Tota": (BG, DIM),  # так этот цвет называется в far2l 2.6.x
    "Panel.Info.Selected": (SURF, YEL),
    "Panel.DragText": (ACC_BG, BRIGHT),
    "Panel.Scrollbar": (BG, SCROLL),
    "Panel.Box": (BG, LINE),
    "Panel.ScreensNumber": (BG, ACC_FG),
    "HMenu.Text": (SURF, TEXT),
    "HMenu.Text.Selected": (ACC_BG, BRIGHT),
    "HMenu.Highlight": (SURF, ACC_FG),
    "HMenu.Highlight.Selected": (ACC_BG, YEL_HI),
    "Menu.Text": (DLG, TEXT),
    "Menu.Text.Selected": (ACC_BG, BRIGHT),
    "Menu.Text.Disabled": (DLG, DIS_DLG),
    "Menu.Highlight": (DLG, ACC_FG),
    "Menu.Highlight.Selected": (ACC_BG, YEL_HI),
    "Menu.Box": (DLG, DIS),
    "Menu.Title": (DLG, BRIGHT),
    "Menu.Scrollbar": (DLG, DIS_DLG),
    "Menu.Arrows": (DLG, ACC_FG),
    "Menu.Arrows.Disabled": (DLG, DIS_DLG),
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
    "Viewer.Scrollbar": (BG, SCROLL),
    "Editor.Text": (BG, TEXT),
    "Editor.Text.Selected": (CURSOR, BRIGHT),
    "Editor.Status": (SURF, TEXT),
    "Editor.LineNumber": (BG, LINENO),
    "Editor.Scrollbar": (BG, SCROLL),
    "Help.Text": (DLG, TEXT),
    "Help.Text.Highlight": (DLG, BRIGHT),
    "Help.Topic": (DLG, ACC_FG),
    "Help.Topic.Selected": (ACC_BG, BRIGHT),
    "Help.Box": (DLG, DIS),
    "Help.Box.Title": (DLG, BRIGHT),
    "Help.Scrollbar": (DLG, DIS_DLG),
    "Not.Used": (BG, DIS),
    # Значения после коррекции контраста (см. DIS_* выше).
    "Dialog.Disabled": (DLG, DIS_DLG),
    "Dialog.List.Disabled": (DLG, DIS_DLG),
    "Dialog.List.Arrows.Disabled": (DLG, DIS_DLG),
    "Dialog.List.Scrollbar": (DLG, DIS_DLG),
    "Dialog.Combo.Disabled": (SURF, DIS_SURF),
    "Dialog.Combo.Arrows.Disabled": (SURF, DIS_SURF),
    "Dialog.Combo.Scrollbar": (SURF, DIS_SURF),
    "Dialog.Edit.Disabled": (EDIT_DIS, DIS_EDIT),
}

# Семейства для ключей, которых нет в правилах (могут появиться в новых версиях far2l):
# фон, текст, акцент, рамка, неактивный, фон выбранного, текст выбранного.
FAMILIES = {
    "Panel": (BG, TEXT, ACC_FG, LINE, DIS, CURSOR, BRIGHT),
    "Menu": (DLG, TEXT, ACC_FG, DIS, DIS_DLG, ACC_BG, BRIGHT),
    "HMenu": (SURF, TEXT, ACC_FG, DIS, DIS_SURF, ACC_BG, BRIGHT),
    "Help": (DLG, TEXT, ACC_FG, DIS, DIS_DLG, ACC_BG, BRIGHT),
    "Dialog": (DLG, TEXT, ACC_FG, DIS, DIS_DLG, ACC_BG, BRIGHT),
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


# Запасные 16-цветные индексы нужны, когда far2l рисует без TrueColor: ключ --norgb, а в 2.8 ещё
# и терминал с TERM=screen* (tmux, GNU screen). Тогда far2l отдаёт терминалу одну палитру:
# цвета 0–7 из [background], 8–15 из [foreground] — по ней индексы и подбираются.
TTY_PALETTE = PALETTE_BG[:8] + PALETTE_FG[8:]
# Фон, для которого ближайший индекс не годится: курсор и поля ввода иначе слились бы с фоном.
INDEX_BG_OVERRIDE = {CURSOR: 1, EDIT: 8}
# Цвет имени файла под курсором без TrueColor (белый на синем курсоре): цвета типов файлов
# на любом фоне курсора из 16 цветов читались бы плохо.
CURSOR_FALLBACK_FG = 15
MIN_CONTRAST = 3.0


def luminance(h):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


GRAY_INDICES = (0, 7, 8, 15)


def _by_distance(h, palette):
    """Индексы палитры по близости к цвету. Серые цвета темы ищутся только среди серых индексов:
    иначе, например, рамка #55555c по расстоянию в RGB оказалась бы ближе к зелёному."""
    c = rgb(h)
    pool = GRAY_INDICES if max(c) - min(c) <= 16 else range(16)
    return sorted(pool, key=lambda i: sum((a - b) ** 2 for a, b in zip(c, rgb(palette[i]))))


def index_pair(bg, fg):
    """Запасные индексы фона и текста: ближайшие по цвету в палитре терминала, причём текст
    берётся ближайший из тех, что читаются на выбранном фоне (контраст не ниже 3:1)."""
    b = INDEX_BG_OVERRIDE.get(bg.lower(), _by_distance(bg, TTY_PALETTE)[0])
    order = [i for i in _by_distance(fg, TTY_PALETTE) if i != b]
    f = next((i for i in order if contrast(TTY_PALETTE[i], TTY_PALETTE[b]) >= MIN_CONTRAST),
             max(order, key=lambda i: contrast(TTY_PALETTE[i], TTY_PALETTE[b])))
    return b, f


def expr(bg, fg):
    """Строка цвета в том же формате, в каком far2l сам сохраняет farcolors.ini.
    far2l читает её до «;»: RGB-цвета плюс запасные 16-цветные индексы."""
    b, f = rgb(bg), rgb(fg)
    bi, fi = index_pair(bg, fg)
    return (f"background:{bg.lower()} foreground:{fg.lower()}, B_{NAMES[bi]} | F_{NAMES[fi]}; "
            f"back_rgb({b[0]}, {b[1]}, {b[2]}) | fore_rgb({f[0]}, {f[1]}, {f[2]})")


def farcolors_text(keys):
    """Текст farcolors.ini для заданных имён цветов и список имён, цвет которых угадан."""
    lines = ["[farcolors]"]
    guessed = []
    for k in sorted(keys):
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
