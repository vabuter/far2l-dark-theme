#!/usr/bin/env python3
"""Снимки far2l без графического экрана: запускает far2l в tmux (TTY-режим, TrueColor)
на КОПИИ каталога настроек и демонстрационных файлах, снимает несколько экранов
и рисует их в PNG. Настоящие настройки и файлы пользователя не меняются.

  python3 tools/snapshot.py --out /tmp/far2l-shots

Экраны: panels (панели с курсором и отмеченными файлами), menu (F9), dialog (F7),
warning (красное предупреждение: попытка создать уже существующую папку),
delete (F8 — подтверждение удаления, отменяется), editor (редактор с подсветкой Python).
Для каждого экрана: NAME.ans (сырой вывод с цветами) и NAME.png (если есть Pillow),
плюс сводка самых частых цветов фона/текста в stdout — по ней можно проверить тему
даже без просмотра картинок (фон панелей темы — #1d1d20).

Нужны: far2l, tmux. Для PNG — Pillow (pip install pillow) и моноширинный TTF-шрифт.
"""
import argparse
import collections
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True  # не оставлять __pycache__ в репозитории
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from install import default_config_dir  # noqa: E402

COLS, ROWS = 150, 40
SGR = re.compile(r"\x1b\[([0-9;]*)m")

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
    print(f"Файлов: {Scanner(os.getcwd()).count()}", 3.14, True)
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


class Tmux:
    def __init__(self, sock):
        self.base = ["tmux", "-L", sock]

    def start(self, cmd):
        subprocess.run(self.base + ["-f", "/dev/null", "new-session", "-d", "-x", str(COLS), "-y", str(ROWS), cmd],
                       check=True)

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


def parse(ans):
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
                        col, i = xterm256(p[i + 2]), i + 2
                    if c == 38:
                        fg = col
                    else:
                        bg = col
                elif 30 <= c <= 37 or 90 <= c <= 97:
                    fg = xterm256(c - 30 if c < 90 else c - 82)
                elif 40 <= c <= 47 or 100 <= c <= 107:
                    bg = xterm256(c - 40 if c < 100 else c - 92)
                i += 1
        row += [(ch, fg, bg) for ch in line[pos:]]
        grid.append(row)
    return grid


def hexc(c):
    return "default" if c is None else "#%02x%02x%02x" % c


def summary(name, grid):
    bgs = collections.Counter(hexc(b) for row in grid for _, _, b in row)
    fgs = collections.Counter(hexc(f) for row in grid for ch, f, _ in row if ch.strip())
    total = sum(bgs.values()) or 1
    top_bg = ", ".join(f"{c} {n * 100 // total}%" for c, n in bgs.most_common(4))
    top_fg = ", ".join(f"{c}" for c, _ in fgs.most_common(6))
    print(f"{name:8} фон: {top_bg}\n{'':8} текст: {top_fg}")


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
            d.rectangle([x * cw, y * ch, (x + 1) * cw - 1, (y + 1) * ch - 1], fill=bg or (0, 0, 0))
            if c.strip():
                d.text((x * cw, y * ch + 1), c, font=font, fill=fg or (200, 200, 200))
    img.save(path)
    return True


def main():
    ap = argparse.ArgumentParser(description="Снимки экранов far2l в tmux")
    ap.add_argument("--config-dir", default=None, help="каталог настроек far2l (копируется, не меняется)")
    ap.add_argument("--out", required=True, help="куда сохранить снимки")
    ap.add_argument("--workdir", default=None, help="временный каталог (по умолчанию системный temp)")
    ap.add_argument("--keep", action="store_true", help="не удалять временный каталог")
    a = ap.parse_args()

    for tool in ("far2l", "tmux"):
        if not shutil.which(tool):
            sys.exit(f"нужен {tool} в PATH")
    cfg = os.path.abspath(os.path.expanduser(a.config_dir)) if a.config_dir else default_config_dir()
    if not os.path.isdir(cfg):
        sys.exit(f"нет каталога настроек: {cfg}")
    work = tempfile.mkdtemp(prefix="far2l-snapshot-", dir=a.workdir)
    profile = os.path.join(work, "profile")
    shutil.copytree(cfg, os.path.join(profile, ".config"), symlinks=True)
    left, right, sample = make_demo(os.path.join(work, "demo"))
    os.makedirs(a.out, exist_ok=True)

    env = f"env FARSETTINGS={shlex.quote(profile)} TERM=xterm-256color COLORTERM=truecolor"
    far = "far2l --tty --nodetect --mortal"
    tm = Tmux(f"far2l-snapshot-{os.getpid()}")
    shots = {}
    try:
        tm.start(f"cd {shlex.quote(right)} && {env} {far} -cd {shlex.quote(left)} -cd {shlex.quote(right)}")
        time.sleep(2.5)
        tm.keys("Escape", "Home", "Down", "Down", "Down", "Down", "Down", "Down", "Down", "Down", "Down", "Down",
                "Insert", "Insert", pause=0.15)
        time.sleep(0.8)
        shots["panels"] = tm.capture()
        tm.keys("F9", "Down")
        shots["menu"] = tm.capture()
        tm.keys("Escape", "Escape", "F7")
        shots["dialog"] = tm.capture()
        # Ошибка «папка уже существует» — красный диалог-предупреждение, ничего не меняет.
        tm.text("Documents")
        tm.keys("Enter", pause=1)
        shots["warning"] = tm.capture()
        tm.keys("Escape", "Escape", "F8")
        shots["delete"] = tm.capture()
        tm.keys("Escape")
        tm.kill()
        tm = Tmux(f"far2l-snapshot-{os.getpid()}-editor")
        tm.start(f"cd {shlex.quote(right)} && {env} {far} -e {shlex.quote(sample)}")
        time.sleep(2.5)
        tm.keys("Down", "Down", "Down", "Down", "Down", "Down", "Down", "Down", "Down", "Down", "End", pause=0.1)
        time.sleep(0.8)
        shots["editor"] = tm.capture()
    finally:
        tm.kill()
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)

    pngs = True
    for name, ans in shots.items():
        with open(os.path.join(a.out, f"{name}.ans"), "w", encoding="utf-8") as fh:
            fh.write(ans)
        grid = parse(ans)
        summary(name, grid)
        pngs = render(grid, os.path.join(a.out, f"{name}.png")) and pngs
    print(f"снимки: {a.out}" + ("" if pngs else " (только .ans — для PNG установите Pillow)"))


if __name__ == "__main__":
    main()
