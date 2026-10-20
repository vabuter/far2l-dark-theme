"""Шаги установки. Каждый шаг идемпотентен: повторный запуск даёт тот же результат."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from . import colors
from .detect import ROOT, data_dirs, far2l_env
from .ini import Ini, write_atomic

THEME_NAME = "GNOME Graphite"
HRD_NAME = "graphite"
MARKER = "# installed by far2l-dark-theme"
ICON_PREFIX = "far2l"
# id .desktop-файла -> (имя иконки, файл в icons/). Ярлыки «(Terminal)» есть в Debian и в сборках из исходников.
DESKTOP_ICONS = {
    "far2l.desktop": ("far2l-graphite", "far2l-graphite.svg"),
    "far2ledit.desktop": ("far2ledit-graphite", "far2ledit-graphite.svg"),
    "far2l-tty.desktop": ("far2l-graphite", "far2l-graphite.svg"),
    "far2ledit-tty.desktop": ("far2ledit-graphite", "far2ledit-graphite.svg"),
}


def theme_file(cfg):
    return os.path.join(cfg, "settings", "themes", THEME_NAME, "farcolors.ini")


def theme_present(cfg):
    """Стоит ли тема (полностью или частично) в этом каталоге настроек."""
    cur = Ini(os.path.join(cfg, "settings", "colors.ini")).get("Colors", "CurrentTheme")
    return (cur == THEME_NAME or os.path.isfile(theme_file(cfg))
            or os.path.isfile(os.path.join(cfg, "plugins", "colorer", f"{HRD_NAME}.hrd")))


def legacy_file(cfg):
    return os.path.join(cfg, "settings", "farcolors.ini")


# --- цвета интерфейса ------------------------------------------------------------------------

def color_targets(profile):
    """Куда писать цвета: theme (каталог темы + CurrentTheme) и/или legacy (settings/farcolors.ini)."""
    if profile is None:
        return {"theme", "legacy"}
    return {"theme"} if profile["uses_themes"] else {"theme", "legacy"}


def step_colors(cfg, profile, keys, log):
    text, guessed = colors.farcolors_text(keys)
    targets = color_targets(profile)
    # Каталог темы и CurrentTheme пишутся всегда: в 2.8+ это основной путь, в 2.6 — задел на обновление far2l.
    write_atomic(theme_file(cfg), text)
    write_atomic(os.path.join(os.path.dirname(theme_file(cfg)), "author.txt"),
                 "Very dark graphite theme in GNOME / libadwaita dark colors.\n"
                 "https://github.com/vabuter/far2l-dark-theme\n", mode=0o644)
    ini = Ini(os.path.join(cfg, "settings", "colors.ini"))
    ini.set("Colors", {"CurrentTheme": THEME_NAME, "CurrentThemeIsSystemWide": "0"})
    ini.save()
    if "legacy" in targets:
        write_atomic(legacy_file(cfg), text)
        log("ok", f"цвета интерфейса: {len(keys)} цветов в settings/farcolors.ini"
                  + (" (эта версия far2l не поддерживает темы)" if profile else ""))
    if profile is None or profile["uses_themes"]:
        log("ok", f"тема «{THEME_NAME}»: {len(keys)} цветов, выбрана текущей")
    if guessed:
        log("!", f"нет явного правила для {len(guessed)} цветов, подобрано по названию: " + ", ".join(guessed))


def step_palette(cfg, log):
    write_atomic(os.path.join(cfg, "palette.ini"), colors.palette_text())
    log("ok", "базовая палитра 16 цветов: palette.ini")


# --- раскраска файлов ------------------------------------------------------------------------

GROUP_RE = re.compile(r"(Colors/Highlight/(Group|LastGroup)\d+|SortGroups/(UpperGroup|LowerGroup)\d+)")
SLOTS = ("NormalColor", "SelectedColor", "CursorColor", "SelectedCursorColor")
ALL64 = 0xFFFFFFFFFFFFFFFF
FG_TRUECOLOR, BG_TRUECOLOR = 0x100, 0x200
BG_BITS = 0xFFFFFF0000000000 | 0xF0 | BG_TRUECOLOR       # индекс, флаг и RGB фона
FG_ONLY_MASK = ALL64 & ~BG_BITS & 0x000000FFFFFFFFFF     # всё, кроме фона


def highlight_groups(ini):
    return [s for s in ini.sections() if GROUP_RE.fullmatch(s)]


def parse_num(v, default=0):
    """Как GetULL в far2l: '0x…' — шестнадцатеричное, иначе десятичное."""
    if v is None:
        return default
    v = v.strip()
    try:
        return int(v[2:], 16) if v.startswith("0x") else int(v, 10)
    except ValueError:
        return 0


def hexnum(n):
    return "0x%x" % n


def normalize_slot(color, mask):
    """Цвет и маска так, как их видит far2l после загрузки (hilight.cpp, код совместимости
    для настроек без масок, far2l до 2.6.2)."""
    if mask:
        return color, mask
    mask = ALL64
    if color & 0x0F00:
        mask ^= 0x000000FFFFFF000F | FG_TRUECOLOR
    if color & 0xF000:
        mask ^= 0xFFFFFF00000000F0 | BG_TRUECOLOR
    color &= 0xFFFFFFFFFFFF00FF
    if color & 0xFFFFFF0000000000:
        color |= BG_TRUECOLOR
    if color & 0x000000FFFFFF0000:
        color |= FG_TRUECOLOR
    return color, mask


def legacy_blue_bg(color, mask):
    """Непрозрачный синий фон (индекс 1) из старых групп far2l: на тёмной теме это синие полосы."""
    return (mask & 0xF0) and (color & 0xF0) == 0x10 and not (color & BG_TRUECOLOR) and not (color >> 40)


def _bgr(hexcolor):
    r, g, b = colors.rgb(hexcolor)
    return (b << 16) | (g << 8) | r


def cursor_color(normal):
    """Цвет имени под курсором: RGB обычного цвета файла (индексный цвет пересчитывается через
    палитру темы) плюс запасной индекс, который читается на курсоре без TrueColor."""
    rgb = (normal >> 16) & 0xFFFFFF if normal & FG_TRUECOLOR else _bgr(colors.PALETTE_FG[normal & 0xF])
    return (rgb << 16) | FG_TRUECOLOR | (normal & 0xF000) | colors.CURSOR_FALLBACK_FG


def highlight_plan(ini):
    """Что надо поменять в группах раскраски: {секция: {ключ: значение}}.
    1) у старых групп убирается синий фон, оставшийся от far2l до 2.6.2;
    2) цвет имени под курсором = обычный цвет файла (только текст; фон курсора берётся из темы).
    Пустую маску far2l считает «маски нет» и включает старый режим совместимости, поэтому
    маска 0 никогда не записывается."""
    plan = {}
    for sec in highlight_groups(ini):
        g = ini.items(sec)
        changes, slots = {}, {}
        for slot in SLOTS:
            if slot not in g:
                continue
            c0, m0 = parse_num(g[slot]), parse_num(g.get(slot + "Mask"))
            c, m = normalize_slot(c0, m0)
            if c & 0xFF and legacy_blue_bg(c, m) and m & ~BG_BITS:
                m &= ~BG_BITS
            slots[slot] = (c, m)
            if (c & 0xFF) and (c, m) != (c0, m0):
                changes[slot], changes[slot + "Mask"] = hexnum(c), hexnum(m)
        if "NormalColor" in slots and "CursorColor" in slots:
            n, nm = slots["NormalColor"]
            cur, _ = slots["CursorColor"]
            if (n & 0xFF) and (cur & 0xFF) and (nm & 0xF):
                target = (cursor_color(n), FG_ONLY_MASK)
                if (parse_num(g.get("CursorColor")), parse_num(g.get("CursorColorMask"))) != target:
                    changes["CursorColor"], changes["CursorColorMask"] = hexnum(target[0]), hexnum(target[1])
                else:
                    changes.pop("CursorColor", None)
                    changes.pop("CursorColorMask", None)
        if changes:
            plan[sec] = changes
    return plan


def step_highlight(cfg, log):
    path = os.path.join(cfg, "settings", "colors.ini")
    ini = Ini(path)
    groups = highlight_groups(ini)
    if not groups:
        log("!", "групп раскраски файлов нет (far2l ещё не запускался) — шаг пропущен")
        return False
    plan = highlight_plan(ini)
    for sec, changes in plan.items():
        ini.set(sec, changes)
    if plan:
        ini.save()
    log("ok", f"раскраска файлов: {len(groups)} групп, изменено {len(plan)}")
    return True


# --- Colorer ---------------------------------------------------------------------------------

def _local(tag):
    return tag.rsplit("}", 1)[-1]


def check_hrd(path):
    """Ошибка в схеме, или None. Сломанную схему Colorer заменяет схемой default (синий редактор);
    а ошибка в файле UserHrdPath в far2l 2.6 выключает Colorer насовсем (Enabled=0)."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        return f"не читается: {e}"
    if _local(root.tag) != "hrd":
        return "корневой элемент не <hrd>"
    names = {a.get("name") for a in root if _local(a.tag) == "assign"}
    if "def:Text" not in names:
        return "нет def:Text"
    with open(path, encoding="utf-8") as fh:
        if re.search(r"#0{6}\b", fh.read()):
            return "#000000 в 2.6 означает «цвет не задан»"
    return None


def check_hrd_sets(path, want_link=None):
    """Ошибка в файле <hrd-sets> (UserHrdPath), или None."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        return f"не читается: {e}"
    if _local(root.tag) != "hrd-sets":
        return "корневой элемент не <hrd-sets>"
    for hrd in root:
        if _local(hrd.tag) == "hrd" and hrd.get("class") == "rgb" and hrd.get("name") == HRD_NAME:
            links = [loc.get("link", "") for loc in hrd if _local(loc.tag) == "location"]
            if not links:
                return "у схемы graphite нет <location>"
            for link in links:
                if not os.path.isabs(link) or not os.path.isfile(link):
                    return f"ссылка на схему не абсолютная или файла нет: {link}"
                if want_link and not (os.path.exists(want_link) and os.path.samefile(link, want_link)):
                    return f"ссылка ведёт не на установленную схему: {link}"
            return None
    return "схема rgb/graphite не зарегистрирована"


def expand_path(value):
    """Путь из config.ini так, как его понимает Colorer: без кавычек, с подстановкой ~ и $VAR."""
    v = (value or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return os.path.abspath(os.path.expanduser(os.path.expandvars(v))) if v else ""


def user_hrds(value, log):
    """Схемы пользователя из прежнего UserHrdPath, кроме graphite (он пишется заново).
    Поддерживаются файл <hrd-sets> (в том числе наш user-hrd.xml от прошлого запуска)
    и каталог *.hrd (так умеет far2l 2.7+; в 2.6 он превращается в записи <hrd-sets>)."""
    path = expand_path(value)
    if not path:
        return []
    found = []
    if os.path.isdir(path):
        for f in sorted(os.listdir(path)):
            full = os.path.join(path, f)
            if not f.endswith(".hrd") or not os.path.isfile(full):
                continue
            try:
                root = ET.parse(full).getroot()
            except (ET.ParseError, OSError):
                continue
            if _local(root.tag) == "hrd" and root.get("class") and root.get("name"):
                h = ET.Element("hrd", {"class": root.get("class"), "name": root.get("name"),
                                       "description": root.get("description") or root.get("name")})
                ET.SubElement(h, "location", {"link": full})
                found.append(h)
    elif os.path.isfile(path):
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError) as e:
            log("!", f"Colorer: прежний UserHrdPath не читается ({e}) — его схемы не перенесены: {value}")
            return []
        if _local(root.tag) != "hrd-sets":
            log("!", f"Colorer: прежний UserHrdPath не <hrd-sets> — его схемы не перенесены: {value}")
            return []
        found = [h for h in root if _local(h.tag) == "hrd"]
    else:
        log("!", f"Colorer: прежний UserHrdPath не найден — его схемы не перенесены: {value}")
        return []
    return [h for h in found if not (h.get("class") == "rgb" and h.get("name") == HRD_NAME)]


def step_colorer(cfg, log, enable=False):
    cdir = os.path.join(cfg, "plugins", "colorer")
    hrd = os.path.join(cdir, f"{HRD_NAME}.hrd")
    sets = os.path.join(cdir, "user-hrd.xml")
    if "$" in hrd:
        log("!", "Colorer пропущен: в пути к настройкам есть «$», Colorer подставил бы туда переменные окружения")
        return
    src = os.path.join(ROOT, "theme", f"{HRD_NAME}.hrd")
    err = check_hrd(src)
    if err:
        raise SystemExit(f"theme/{HRD_NAME}.hrd: {err}")
    ini = Ini(os.path.join(cdir, "config.ini"))
    cur = ini.items("Settings")
    keep = user_hrds(cur.get("UserHrdPath", ""), log)

    os.makedirs(cdir, exist_ok=True)
    with open(src, encoding="utf-8") as fh:
        write_atomic(hrd, fh.read(), mode=0o644)
    root = ET.Element("hrd-sets")
    ours = ET.SubElement(root, "hrd", {"class": "rgb", "name": HRD_NAME, "description": "GNOME Graphite"})
    ET.SubElement(ours, "location", {"link": hrd})
    root.extend(keep)
    ET.indent(root) if hasattr(ET, "indent") else None
    write_atomic(sets, '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n",
                 mode=0o644)
    for path, check in ((hrd, check_hrd), (sets, lambda p: check_hrd_sets(p, hrd))):
        err = check(path)
        if err:
            raise SystemExit(f"Colorer: {path}: {err} — config.ini не изменён")
    values = {"HrdNameTm": HRD_NAME, "HrdName": "black", "UserHrdPath": sets, "TrueMod": "1"}
    if enable:
        values["Enabled"] = "1"
    ini.set("Settings", values)
    ini.save()
    log("ok", f"подсветка синтаксиса Colorer: схема «{HRD_NAME}»"
              + (f" (сохранены схемы пользователя: {len(keep)})" if keep else ""))
    if not enable and cur.get("Enabled", "1").strip() == "0":
        log("!", "Colorer выключен (Enabled=0) — подсветки в редакторе не будет. "
                 "Включить: F11 → Colorer → Настройки, или повторить установку с --enable-colorer")


# --- иконки ----------------------------------------------------------------------------------

# Где ярлыки лежат всегда, даже если в окружении урезан XDG_DATA_DIRS (IDE, песочницы).
STANDARD_DATA_DIRS = ("/usr/local/share", "/usr/share")
MARKER_RE = re.compile(r"^# installed by far2l-dark-theme(?:; source=(.*))?\s*$", re.M)


def is_ours(text):
    """Переопределение, созданное установщиком (метка или иконка темы — у первой версии метки не было)."""
    return MARKER_RE.search(text) is not None or re.search(r"^Icon=far2l(edit)?-graphite\s*$", text, re.M) is not None


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def system_desktop(desktop_id, dhome):
    user = os.path.realpath(os.path.join(dhome, "applications", desktop_id))
    dirs = data_dirs() + [d for d in STANDARD_DATA_DIRS if d not in data_dirs()]
    for d in dirs:
        p = os.path.join(d, "applications", desktop_id)
        if os.path.isfile(p) and os.path.realpath(p) != user:
            return p
    return None


def _body(text):
    """Содержимое .desktop без нашей метки и строки Icon= — для сравнения с системным."""
    return [l.strip() for l in text.split("\n")
            if l.strip() and not MARKER_RE.fullmatch(l.strip()) and not l.strip().startswith("Icon=")]


def desktop_source(desktop_id, dhome):
    """(текст исходного .desktop, откуда он) или None.

    Собственный файл пользователя в ~/.local/share/applications — основа переопределения, его правки
    сохраняются и при повторных запусках (source=user). Переопределение, сделанное из системного
    ярлыка, каждый раз строится заново из системного: после обновления far2l он мог измениться."""
    user = os.path.join(dhome, "applications", desktop_id)
    sysfile = system_desktop(desktop_id, dhome)
    if os.path.isfile(user):
        text = _read(user)
        if not is_ours(text):
            return text, "user"
        m = MARKER_RE.search(text)
        if m and m.group(1) == "user":
            return text, "user"
        if m and m.group(1) is None and (not sysfile or _body(text) != _body(_read(sysfile))):
            # Метка прежней версии установщика без источника: если файл отличается от системного,
            # это ярлык пользователя — его правки сохраняем.
            return text, "user"
    return (_read(sysfile), sysfile) if sysfile else None


def set_desktop_icon(text, icon, source="system"):
    out, group, done = [], None, False
    for line in text.split("\n"):
        s = line.strip()
        if MARKER_RE.fullmatch(s):
            continue
        if s.startswith("[") and s.endswith("]"):
            group = s
        elif group == "[Desktop Entry]" and s.startswith("Icon="):
            line, done = f"Icon={icon}", True
        out.append(line)
    if not done:
        i = next(n for n, l in enumerate(out) if l.strip() == "[Desktop Entry]")
        out.insert(i + 1, f"Icon={icon}")
    out.insert(0, f"{MARKER}; source={source}")
    return "\n".join(out)


def step_icons(dhome, log):
    if sys.platform == "darwin":
        log("-", "иконки: на macOS не ставятся (только Linux/XDG)")
        return
    idir = os.path.join(dhome, "icons", "hicolor", "scalable", "apps")
    adir = os.path.join(dhome, "applications")
    done = 0
    for desktop_id, (icon, svg) in DESKTOP_ICONS.items():
        target = os.path.join(adir, desktop_id)
        src = desktop_source(desktop_id, dhome)
        if not src:
            if os.path.isfile(target) and not os.path.islink(target):
                m = MARKER_RE.search(_read(target))
                if m and m.group(1) and m.group(1) != "user" and not os.path.exists(m.group(1)):
                    os.remove(target)  # системного ярлыка больше нет — наш устаревший не оставляем
                    log("ok", f"{desktop_id}: ярлыка больше нет в системе, переопределение убрано")
            continue
        text, source = src
        os.makedirs(idir, exist_ok=True)
        write_atomic(os.path.join(idir, svg), _read(os.path.join(ROOT, "icons", svg)), mode=0o644,
                     follow_symlinks=False)
        # Ссылку (например, на системный ярлык) не продолжаем: заменяем её своим файлом.
        write_atomic(target, set_desktop_icon(text, icon, source), mode=0o644, follow_symlinks=False)
        log("ok", f"иконка {icon}: {desktop_id}" + (" (на основе вашего ярлыка)" if source == "user" else ""))
        done += 1
    if not done:
        log("!", "иконки: .desktop-файлы far2l не найдены (графический модуль far2l не установлен?) — пропущено")
        return
    hic = os.path.join(dhome, "icons", "hicolor")
    os.utime(hic)  # GTK перечитывает тему иконок по времени изменения каталога темы
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", adir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --- первый запуск far2l ---------------------------------------------------------------------

class _Tmux:
    def __init__(self, sock):
        self.base = ["tmux", "-S", sock]

    def run(self, *args, **kw):
        return subprocess.run(self.base + list(args), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, **kw)

    def alive(self):
        return self.run("has-session").returncode == 0

    def screen(self):
        return self.run("capture-pane", "-p").stdout

    def key(self, k):
        self.run("send-keys", k)

    def stable_screen(self, timeout=6.0):
        """Ждёт, пока экран перестанет меняться; возвращает его (или None, если far2l завершился)."""
        prev, t0 = None, time.time()
        while time.time() - t0 < timeout:
            if not self.alive():
                return None
            cur = self.screen()
            if cur == prev and cur.strip():
                return cur
            prev = cur
            time.sleep(0.5)
        return prev


def short_tmpdir(prefix, longest_name="tmux.sock"):
    """Временный каталог с коротким путём: путь Unix-сокета ограничен ~100 байтами,
    а $TMPDIR в песочницах агентов бывает очень длинным."""
    d = tempfile.mkdtemp(prefix=prefix)
    if len(os.path.join(d, longest_name).encode()) >= 100 and os.path.isdir("/tmp"):
        try:
            short = tempfile.mkdtemp(prefix=prefix, dir="/tmp")
        except OSError:
            return d  # /tmp недоступен: остаёмся в длинном каталоге, tmux тогда сообщит об ошибке
        os.rmdir(d)
        d = short
    return d


def bootstrap(cfg, timeout=40):
    """Первый запуск far2l в tmux (терминальный режим) и выход, чтобы он создал штатные настройки.

    Enter нажимается только когда после F10 появился диалог выхода: случайный Enter
    в вопросе про OSC52 включил бы его в настоящих настройках пользователя."""
    env = far2l_env(cfg)
    if env is None or not shutil.which("tmux") or not shutil.which("far2l"):
        return False
    env["TERM"] = "xterm-256color"
    empty, tm = None, None
    deadline = time.time() + timeout
    try:
        empty = short_tmpdir("f2boot-")
        tm = _Tmux(os.path.join(empty, "tmux.sock"))  # сокет удаляется вместе с временным каталогом
        os.makedirs(os.path.join(empty, "cwd"))
        subprocess.run(tm.base + ["-f", "/dev/null", "new-session", "-d", "-x", "120", "-y", "35",
                                  "-c", os.path.join(empty, "cwd"), "far2l --tty --nodetect --mortal"],
                       env=env, check=True)
        while time.time() < deadline and tm.alive():
            # Закрыть модальные окна первого запуска (справку, вопрос про OSC52): Escape, пока экран меняется.
            base = tm.stable_screen()
            for _ in range(4):
                if base is None:
                    break
                tm.key("Escape")
                after = tm.stable_screen()
                if after == base:
                    break
                base = after
            if base is None:
                break
            tm.key("F10")
            dialog = tm.stable_screen()
            if dialog is None:
                break
            if dialog != base:
                tm.key("Enter")
                for _ in range(20):
                    if not tm.alive():
                        break
                    time.sleep(0.3)
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        if tm:
            tm.run("kill-server")
        if empty:
            shutil.rmtree(empty, ignore_errors=True)
    return bool(highlight_groups(Ini(os.path.join(cfg, "settings", "colors.ini"))))
