#!/usr/bin/env python3
"""Снимки far2l без участия человека: far2l запускается на КОПИИ каталога настроек и
демонстрационных файлах, снимаются несколько экранов, результат — PNG и сводка цветов.
Настоящие настройки и файлы пользователя не меняются.

  python3 tools/snapshot.py --out /tmp/far2l-shots                  # режим выбирается сам
  python3 tools/snapshot.py --out /tmp/far2l-shots --backend gui    # графическое окно (wx) в Xvfb
  python3 tools/snapshot.py --out /tmp/far2l-shots --backend tty    # терминальный режим в tmux

Режимы:
  gui — настоящее графическое окно far2l на виртуальном X-сервере. Так far2l выглядит
        в GNOME (X11 и Wayland — рисует один и тот же модуль wx). Нужны: Xvfb, xdotool,
        ImageMagick (import) и Pillow. Предпочтительный режим.
  tty — far2l в tmux с TrueColor. Индексные цвета пересчитываются через palette.ini так,
        как их покажет терминал. Старые tmux (например, 3.3a в Debian 12) не отдают стёртые
        клетки в конце строки — far2l 2.6 стирает так пустые места редактора. Такие клетки
        в сводке идут отдельной строкой «не захвачено tmux», на PNG они фиолетовые: это не ошибка темы.

Экраны: panels (панели с курсором и отмеченными файлами), menu (F9), dialog (F7),
warning (красное предупреждение: попытка создать уже существующую папку),
delete (F8 — подтверждение удаления, отменяется), editor (редактор с подсветкой Python).
"""
import argparse
import collections
import ctypes
import ctypes.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True  # не оставлять __pycache__ в репозитории
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from far2l_theme.detect import default_config_dir, gui_module  # noqa: E402
from far2l_theme.ini import Ini  # noqa: E402
from far2l_theme.steps import short_tmpdir  # noqa: E402

COLS, ROWS = 150, 40          # размер терминала (tty)
GUI_COLS, GUI_ROWS = 120, 36  # размер окна в символах (gui)
SGR = re.compile(r"\x1b\[([0-9;]*)m")
TRIMMED = "trimmed"

SAMPLE_PY = '''# Демонстрация подсветки синтаксиса
import os
from pathlib import Path


class Scanner:
    """Обходит каталог и считает файлы."""

    def __init__(self, root: str, limit: int = 100):
        self.root = Path(root)
        self.limit = limit

    def count(self) -> int:
        total = 0
        for path in self.root.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                total += 1  # TODO: учитывать симлинки
        return min(total, self.limit)


if __name__ == "__main__":
    print(f"Файлов: {Scanner(os.getcwd()).count()}", 3.14, True, 0xFF)
'''


def make_demo(root):
    left, right = os.path.join(root, "home"), os.path.join(root, "project")
    for d in ("Documents", "Downloads", "Music", "Pictures", ".config", ".cache"):
        os.makedirs(os.path.join(left, d), exist_ok=True)
    for d in ("src", "tests", "docs", ".git"):
        os.makedirs(os.path.join(right, d), exist_ok=True)
    files = {
        left: ["notes.txt", "photo.jpg", "song.mp3", "movie.mp4", "backup.tar.gz", "archive.zip",
               "report.pdf", ".bashrc", ".profile", "todo.md"],
        right: ["README.md", "Makefile", "main.py", "utils.py", "config.yaml", "data.json",
                "LICENSE", ".gitignore", "Cargo.toml", "app.log"],
    }
    for d, names in files.items():
        for n in names:
            with open(os.path.join(d, n), "w", encoding="utf-8") as fh:
                fh.write("demo\n" * (len(n) * 37))
    for d, n in ((left, "install.sh"), (right, "build.sh")):
        p = os.path.join(d, n)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\necho demo\n")
        os.chmod(p, 0o755)
    os.symlink("notes.txt", os.path.join(left, "notes-link.txt"))
    sample = os.path.join(right, "scanner.py")
    with open(sample, "w", encoding="utf-8") as fh:
        fh.write(SAMPLE_PY)
    return left, right, sample


def prepare_profile(cfg, profile, gui):
    """Копия настроек без окон первого запуска; для gui — фиксированные шрифт и размер окна."""
    dst = os.path.join(profile, ".config")
    # Копия без ссылок: far2l в копии ничего не запишет в настоящие файлы (dotfiles и т. п.).
    def dangling(d, names):  # битые ссылки пропускаем; рабочие (в том числе относительные) копируются по содержимому
        return [n for n in names if os.path.islink(os.path.join(d, n)) and not os.path.exists(os.path.join(d, n))]

    shutil.copytree(cfg, dst, symlinks=False, ignore=dangling)

    def put(name, text):
        p = os.path.join(dst, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if os.path.lexists(p):
            os.remove(p)
        with open(p, "w") as fh:
            fh.write(text)

    if not os.path.exists(os.path.join(dst, "settings", "config.ini")):
        put(os.path.join("settings", "config.ini"), "")  # иначе far2l покажет справку «Начало работы»
    if gui:
        put("font", "Monospace 12\n")
        put("winstate", f"1\n-{GUI_COLS}\n-{GUI_ROWS}\n0\n0\n")  # отрицательный размер = в символах


def child_env(profile, extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("FAR2L_")}
    env["FARSETTINGS"] = profile
    env.update(extra or {})
    return env


# --- цвета -----------------------------------------------------------------------------------

def xterm256(n):
    base = [(0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0), (0, 0, 128), (128, 0, 128), (0, 128, 128),
            (192, 192, 192), (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0), (0, 0, 255),
            (255, 0, 255), (0, 255, 255), (255, 255, 255)]
    if n < 16:
        return base[n]
    if n < 232:
        n -= 16
        v = [0, 95, 135, 175, 215, 255]
        return v[n // 36], v[(n // 6) % 6], v[n % 6]
    g = 8 + (n - 232) * 10
    return g, g, g


def terminal_palette(cfg):
    """16 цветов терминала, какими их сделает far2l в TTY-режиме: при TTYPaletteOverride=1
    (по умолчанию) цвета 0–7 берутся из palette.ini [background], 8–15 — из [foreground].
    Порядок индексов ANSI и Windows отличается (красный и синий поменяны местами)."""
    override = Ini(os.path.join(cfg, "settings", "config.ini")).get("Interface", "TTYPaletteOverride", "1")
    pal = Ini(os.path.join(cfg, "palette.ini"))
    fg, bg = pal.items("foreground"), pal.items("background")
    if override == "0" or len(fg) < 16 or len(bg) < 16:
        return [xterm256(i) for i in range(16)]
    win_of_ansi = [0, 4, 2, 6, 1, 5, 3, 7]
    out = []
    for ansi in range(16):
        w = win_of_ansi[ansi % 8] + (ansi // 8) * 8
        h = (bg if ansi < 8 else fg)[str(w)].lstrip("#")
        out.append(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))
    return out


def parse(ans, pal16):
    """Сетка клеток (символ, цвет текста, цвет фона). Атрибуты tmux переносит между строками."""
    grid, fg, bg = [], None, None
    for line in ans.split("\n")[:ROWS]:
        row, pos = [], 0
        for m in SGR.finditer(line):
            row += [(ch, fg, bg) for ch in line[pos:m.start()]]
            pos = m.end()
            p = [int(x) if x else 0 for x in m.group(1).split(";")]
            i = 0
            while i < len(p):
                c = p[i]
                if c == 0:
                    fg = bg = None
                elif c == 39:
                    fg = None
                elif c == 49:
                    bg = None
                elif c in (38, 48) and i + 1 < len(p):
                    if p[i + 1] == 2:
                        col, i = tuple(p[i + 2:i + 5]), i + 4
                    else:
                        n = p[i + 2]
                        col, i = (pal16[n] if n < 16 else xterm256(n)), i + 2
                    if c == 38:
                        fg = col
                    else:
                        bg = col
                elif 30 <= c <= 37 or 90 <= c <= 97:
                    fg = pal16[c - 30 if c < 90 else c - 82]
                elif 40 <= c <= 47 or 100 <= c <= 107:
                    bg = pal16[c - 40 if c < 100 else c - 92]
                i += 1
        row += [(ch, fg, bg) for ch in line[pos:]]
        row += [(" ", None, TRIMMED)] * (COLS - len(row))  # клетки, которые tmux не отдал
        grid.append(row)
    return grid


def hexc(c):
    return "default" if c is None else "#%02x%02x%02x" % c


def summary_tty(name, grid):
    cells = [c for row in grid for c in row]
    total = len(cells) or 1
    trimmed = sum(1 for _, _, b in cells if b == TRIMMED)
    bgs = collections.Counter(hexc(b) for _, _, b in cells if b != TRIMMED)
    fgs = collections.Counter(hexc(f) for ch, f, b in cells if ch.strip() and b != TRIMMED)
    print(f"{name:8} фон: " + ", ".join(f"{c} {n * 100 // total}%" for c, n in bgs.most_common(5))
          + (f"; не захвачено tmux {trimmed * 100 // total}%" if trimmed else ""))
    print(f"{'':8} текст: " + ", ".join(c for c, _ in fgs.most_common(7)))


def summary_png(name, path):
    from PIL import Image
    img = Image.open(path).convert("RGB")
    total = img.width * img.height
    counts = sorted(img.getcolors(total), reverse=True)
    print(f"{name:8} цвета: " + ", ".join("#%02x%02x%02x %d%%" % (c + (n * 100 // total,)) for n, c in counts[:6]))


def find_font():
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", "monospace"], capture_output=True, text=True).stdout
        if out and os.path.isfile(out):
            return out
    except FileNotFoundError:
        pass
    for p in ("/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "/System/Library/Fonts/Menlo.ttc"):
        if os.path.isfile(p):
            return p
    return None


def render(grid, path):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    font_path = find_font()
    font = ImageFont.truetype(font_path, 15) if font_path else ImageFont.load_default()
    cw, ch = 9, 19
    img = Image.new("RGB", (COLS * cw, ROWS * ch), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for y, row in enumerate(grid):
        for x, (c, fg, bg) in enumerate(row[:COLS]):
            fill = (96, 0, 96) if bg == TRIMMED else (bg or (0, 0, 0))
            d.rectangle([x * cw, y * ch, (x + 1) * cw - 1, (y + 1) * ch - 1], fill=fill)
            if c.strip():
                d.text((x * cw, y * ch + 1), c, font=font, fill=fg or (200, 200, 200))
    img.save(path)
    return True


def drive(shots, ui):
    """Один сценарий для обоих режимов. ui: keys(), text(), capture()."""
    ui.keys("Escape", "Home", *["Down"] * 10, "Insert", "Insert", pause=0.15)
    time.sleep(0.8)
    shots["panels"] = ui.capture()
    ui.keys("F9", "Down")
    shots["menu"] = ui.capture()
    ui.keys("Escape", "Escape", "F7")
    shots["dialog"] = ui.capture()
    # Ошибка «папка уже существует» — красный диалог-предупреждение, ничего не меняет.
    ui.text("Documents")
    ui.keys("Enter", pause=1)
    shots["warning"] = ui.capture()
    ui.keys("Escape", "Escape", "F8")
    shots["delete"] = ui.capture()
    ui.keys("Escape")


# --- tty -------------------------------------------------------------------------------------

class Tmux:
    def __init__(self, sock):
        self.base = ["tmux", "-S", sock]  # сокет во временном каталоге — удаляется вместе с ним

    def start(self, cmd, env, cwd):
        subprocess.run(self.base + ["-f", "/dev/null", "new-session", "-d", "-x", str(COLS), "-y", str(ROWS),
                                    "-c", cwd, cmd], check=True, env=env)

    def keys(self, *keys, pause=0.6):
        for k in keys:
            subprocess.run(self.base + ["send-keys", k], check=True)
            time.sleep(pause)

    def text(self, text, pause=0.6):
        subprocess.run(self.base + ["send-keys", "-l", text], check=True)
        time.sleep(pause)

    def capture(self):
        return subprocess.run(self.base + ["capture-pane", "-p", "-e", "-N"], check=True,
                              capture_output=True, text=True).stdout

    def kill(self):
        subprocess.run(self.base + ["kill-server"], stderr=subprocess.DEVNULL)


def shots_tty(profile, left, right, sample):
    sockdir = short_tmpdir("f2snap-", "tmux-editor.sock")  # путь Unix-сокета ограничен ~100 байтами
    # Короткий TMPDIR и для самого far2l: у него тоже есть свои сокеты.
    env = child_env(profile, {"TERM": "xterm-256color", "COLORTERM": "truecolor", "TMPDIR": sockdir})
    far = "far2l --tty --nodetect --mortal"
    q = lambda s: "'" + s.replace("'", "'\\''") + "'"  # noqa: E731
    tm = Tmux(os.path.join(sockdir, "tmux-panels.sock"))
    shots = {}
    try:
        tm.start(f"{far} -cd {q(left)} -cd {q(right)}", env, right)
        time.sleep(2.5)
        drive(shots, tm)
        tm.kill()
        tm = Tmux(os.path.join(sockdir, "tmux-editor.sock"))  # новый сокет: старый сервер ещё может завершаться
        tm.start(f"{far} -e {q(sample)}", env, right)
        time.sleep(2.5)
        tm.keys(*["Down"] * 10, "End", pause=0.1)
        time.sleep(0.8)
        shots["editor"] = tm.capture()
    finally:
        tm.kill()
        shutil.rmtree(sockdir, ignore_errors=True)
    return shots


# --- gui -------------------------------------------------------------------------------------

class Xvfb:
    def __init__(self):
        r, w = os.pipe()
        self.proc = subprocess.Popen(["Xvfb", "-displayfd", str(w), "-screen", "0", "1920x1200x24", "-nolisten", "tcp"],
                                     pass_fds=(w,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(w)
        num = b""
        while not num.endswith(b"\n"):
            chunk = os.read(r, 16)
            if not chunk:
                raise RuntimeError("Xvfb не запустился")
            num += chunk
        os.close(r)
        self.env = {"DISPLAY": ":" + num.decode().strip(), "GDK_BACKEND": "x11"}
        self.window = None
        self.far = None

    def run(self, *args, check=False):
        return subprocess.run(list(args), env=dict(os.environ, **self.env), capture_output=True, check=check)

    def start_far2l(self, args, profile, cwd):
        self.far = subprocess.Popen(["far2l", "--notty"] + args, env=child_env(profile, self.env), cwd=cwd,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            out = self.run("xdotool", "search", "--onlyvisible", "--classname", "far2l").stdout.split()
            if out:
                self.window = out[0].decode()
                break
            if self.far.poll() is not None:
                raise RuntimeError("far2l завершился, не открыв окно")
            time.sleep(0.5)
        else:
            raise RuntimeError("окно far2l не появилось")
        time.sleep(2)
        self.run("xdotool", "windowfocus", "--sync", self.window)  # без оконного менеджера фокус надо дать явно

    def stop_far2l(self):
        if self.far and self.far.poll() is None:
            self.far.terminate()
            try:
                self.far.wait(5)
            except subprocess.TimeoutExpired:
                self.far.kill()
        self.far = None

    def _xtest(self):
        """Нажатия идут через расширение XTEST по коду клавиши, без модификаторов.
        xdotool здесь не годится: с xkeyboard-config ≥ 2.4x он добавляет Alt к F-клавишам."""
        if getattr(self, "_dpy", None) is None:
            find = ctypes.util.find_library
            self._x11 = ctypes.cdll.LoadLibrary(find("X11") or "libX11.so.6")
            self._xt = ctypes.cdll.LoadLibrary(find("Xtst") or "libXtst.so.6")
            self._x11.XOpenDisplay.restype = ctypes.c_void_p
            self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self._x11.XStringToKeysym.restype = ctypes.c_ulong
            self._x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
            self._x11.XKeysymToKeycode.restype = ctypes.c_ubyte
            self._x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            self._x11.XFlush.argtypes = [ctypes.c_void_p]
            self._xt.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
            self._dpy = self._x11.XOpenDisplay(self.env["DISPLAY"].encode())
            if not self._dpy:
                raise RuntimeError("не удалось подключиться к Xvfb")
        return self._dpy

    def _tap(self, keysym, shift=False):
        dpy = self._xtest()
        code = lambda name: self._x11.XKeysymToKeycode(dpy, self._x11.XStringToKeysym(name.encode()))  # noqa: E731
        kc = code(keysym)
        if not kc:
            raise RuntimeError(f"нет клавиши {keysym}")
        seq = ([(code("Shift_L"), 1)] if shift else []) + [(kc, 1), (kc, 0)] + ([(code("Shift_L"), 0)] if shift else [])
        for k, down in seq:
            self._xt.XTestFakeKeyEvent(dpy, k, down, 0)
            self._x11.XFlush(dpy)
            time.sleep(0.03)

    def keys(self, *keys, pause=0.6):
        for k in keys:
            self._tap({"Enter": "Return"}.get(k, k))
            time.sleep(pause)

    def text(self, text, pause=0.6):
        for ch in text:
            self._tap(ch.lower(), shift=ch.isupper())
        time.sleep(pause)

    def capture(self):
        """PNG окна far2l: снимок экрана, обрезанный по окну."""
        time.sleep(0.4)
        geo = self.run("xdotool", "getwindowgeometry", "--shell", self.window).stdout.decode()
        g = dict(line.split("=", 1) for line in geo.split() if "=" in line)
        crop = f"{g['WIDTH']}x{g['HEIGHT']}+{g['X']}+{g['Y']}"
        return self.run("import", "-window", "root", "-crop", crop, "+repage", "png:-", check=True).stdout

    def close(self):
        self.stop_far2l()
        self.proc.terminate()


def shots_gui(profile, left, right, sample):
    x = Xvfb()
    tmpdir = short_tmpdir("f2gui-")
    x.env["TMPDIR"] = tmpdir  # короткий TMPDIR для сокетов самого far2l
    shots = {}
    try:
        x.start_far2l(["-cd", left, "-cd", right], profile, right)
        drive(shots, x)
        x.stop_far2l()
        x.start_far2l(["-e", sample], profile, right)
        x.keys(*["Down"] * 10, "End", pause=0.1)
        shots["editor"] = x.capture()
    finally:
        x.close()
        shutil.rmtree(tmpdir, ignore_errors=True)
    return shots


def gui_missing():
    missing = [t for t in ("Xvfb", "xdotool", "import") if not shutil.which(t)]
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("Pillow")
    if not gui_module():
        missing.append("графический модуль far2l (far2l_gui.so)")
    return missing


def main():
    ap = argparse.ArgumentParser(description="Снимки экранов far2l")
    ap.add_argument("--config-dir", default=None, help="каталог настроек far2l (копируется, не меняется)")
    ap.add_argument("--out", required=True, help="куда сохранить снимки")
    ap.add_argument("--backend", choices=("auto", "gui", "tty"), default="auto")
    ap.add_argument("--workdir", default=None, help="временный каталог (по умолчанию системный temp)")
    ap.add_argument("--keep", action="store_true", help="не удалять временный каталог")
    a = ap.parse_args()

    if not shutil.which("far2l"):
        sys.exit("нужен far2l в PATH")
    backend, missing = a.backend, gui_missing()
    if backend == "auto":
        backend = "tty" if missing else "gui"
        if missing:
            print(f"[-] графический режим недоступен (нет: {', '.join(missing)}), снимаю в терминальном")
    elif backend == "gui" and missing:
        sys.exit("для --backend gui не хватает: " + ", ".join(missing))
    if backend == "tty" and not shutil.which("tmux"):
        sys.exit("нужен tmux в PATH")
    cfg = os.path.abspath(os.path.expanduser(a.config_dir)) if a.config_dir else default_config_dir()
    if not os.path.isdir(cfg):
        sys.exit(f"нет каталога настроек: {cfg}")
    work = tempfile.mkdtemp(prefix="far2l-snapshot-", dir=a.workdir)
    profile = os.path.join(work, "profile")
    prepare_profile(cfg, profile, backend == "gui")
    left, right, sample = make_demo(os.path.join(work, "demo"))
    os.makedirs(a.out, exist_ok=True)
    try:
        shots = (shots_gui if backend == "gui" else shots_tty)(profile, left, right, sample)
        pal16 = terminal_palette(os.path.join(profile, ".config"))
    finally:
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)

    print(f"режим: {backend}")
    pngs = True
    for name, data in shots.items():
        png = os.path.join(a.out, f"{name}.png")
        if backend == "gui":
            with open(png, "wb") as fh:
                fh.write(data)
            summary_png(name, png)
            continue
        with open(os.path.join(a.out, f"{name}.ans"), "w", encoding="utf-8") as fh:
            fh.write(data)
        grid = parse(data, pal16)
        summary_tty(name, grid)
        pngs = render(grid, png) and pngs
    print(f"снимки: {a.out}" + ("" if pngs else " (только .ans — для PNG установите Pillow)"))


if __name__ == "__main__":
    main()
