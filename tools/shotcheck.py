#!/usr/bin/env python3
"""Проверка цветов на снимках tools/snapshot.py: есть ли на экранах цвета темы и нет ли штатных.

  python3 tools/shotcheck.py --dir /tmp/far2l-shots --backend gui
  python3 tools/shotcheck.py --dir /tmp/far2l-shots --backend tty --config-dir ~/.config/far2l

gui — по пикселям PNG (нужен Pillow); tty — по клеткам .ans с пересчётом индексных цветов
через palette.ini (как их покажет терминал). Код выхода 0 — все проверки прошли.
"""
import argparse
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from far2l_theme.detect import default_config_dir  # noqa: E402
from far2l_theme.colors import contrast  # noqa: E402
from tools.snapshot import TRIMMED, hexc, parse, terminal_palette  # noqa: E402

# (экран, слой, цвет, мин. доля, описание); слой: bg — фон клеток (tty) или пиксели (gui), fg — текст (tty).
EXPECT = [
    ("panels", "bg", "#1d1d20", 0.40, "графитовый фон панелей"),
    ("panels", "bg", "#254165", 0.003, "курсор"),
    ("panels", "bg", "#1c71d8", 0.002, "заголовок активной панели"),
    ("menu", "bg", "#36363a", 0.05, "фон меню"),
    ("dialog", "bg", "#36363a", 0.05, "фон диалога"),
    ("warning", "bg", "#a51d2d", 0.03, "красное предупреждение"),
    ("editor", "bg", "#1d1d20", 0.40, "графитовый фон редактора"),
    ("editor", "fg", "#ffa348", 0.0003, "ключевые слова (Colorer, схема graphite)"),
]
FORBID = [
    ("panels", "bg", "#e01b24", 0.0005, "красная строка итога (нет цвета Panel.Info.Tota)"),
    ("panels", "bg", "#000080", 0.0005, "штатный синий фон"),
    ("panels", "bg", "#008080", 0.0005, "штатный бирюзовый курсор"),
    ("editor", "bg", "#000060", 0.0005, "синий фон Colorer по умолчанию"),
]
TOL = 3  # far2l и Colorer округляют цвета на 1–2 единицы


def near(c, want):
    return c is not None and c != TRIMMED and max(abs(x - y) for x, y in zip(c, want)) <= TOL


def hex2rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def fraction_gui(path, layer, color):
    from PIL import Image
    img = Image.open(path).convert("RGB")
    total = img.width * img.height
    want = hex2rgb(color)
    return sum(n for n, c in img.getcolors(total) if near(c, want)) / total


def fraction_tty(cells, layer, color):
    want = hex2rgb(color)
    if layer == "fg":
        pool = [f for ch, f, b in cells if ch.strip() and b != TRIMMED]
    else:
        pool = [b for _, _, b in cells if b != TRIMMED]  # клетки, которые tmux не отдал, не считаем
    return sum(1 for c in pool if near(c, want)) / (len(pool) or 1)


def main():
    ap = argparse.ArgumentParser(description="Проверка цветов на снимках far2l")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--backend", choices=("gui", "tty"), required=True)
    ap.add_argument("--config-dir", default=None, help="каталог настроек (для palette.ini в режиме tty)")
    a = ap.parse_args()
    cfg = os.path.abspath(os.path.expanduser(a.config_dir)) if a.config_dir else default_config_dir()
    pal16 = terminal_palette(cfg)
    cache = {}

    def frac(screen, layer, color):
        if a.backend == "gui":
            return fraction_gui(os.path.join(a.dir, f"{screen}.png"), layer, color)
        if screen not in cache:
            with open(os.path.join(a.dir, f"{screen}.ans"), encoding="utf-8") as fh:
                cache[screen] = [c for row in parse(fh.read(), pal16) for c in row]
        return fraction_tty(cache[screen], layer, color)

    ok = True
    for screen, layer, color, minimum, what in EXPECT:
        f = frac(screen, layer, color)
        ok &= f >= minimum
        print(f"{'PASS' if f >= minimum else 'FAIL'}\t{screen}: {what} ({color})\t{f:.2%}")
    for screen, layer, color, maximum, what in FORBID:
        f = frac(screen, layer, color)
        ok &= f <= maximum
        print(f"{'PASS' if f <= maximum else 'FAIL'}\t{screen}: нет «{what}» ({color})\t{f:.2%}")
    if a.backend == "tty":
        # Текст, который почти не отличается от своего фона, — нечитаем (контраст ниже 1.2:1).
        for screen in ("panels", "menu", "dialog", "warning", "editor"):
            frac(screen, "bg", "#000000")  # заполняет cache
            bad = [(ch, f, b) for ch, f, b in cache[screen]
                   if ch.strip() and f and b and b != TRIMMED and contrast(hexc(f), hexc(b)) < 1.2]
            ok &= not bad
            sample = ", ".join(f"«{ch}» {hexc(f)} на {hexc(b)}" for ch, f, b in bad[:3])
            print(f"{'PASS' if not bad else 'FAIL'}\t{screen}: нет нечитаемого текста\t{len(bad)}"
                  + (f" ({sample})" if bad else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
