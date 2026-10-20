"""Проверка установки (python3 install.py --verify). Только читает файлы."""
import os
import sys

from . import colors
from .detect import ROOT
from .ini import Ini
from .steps import (DESKTOP_ICONS, HRD_NAME, THEME_NAME, check_hrd, check_hrd_sets, color_targets,
                    desktop_source, expand_path, highlight_groups, highlight_plan, legacy_file, theme_file)


def verify(cfg, dhome, profile, keys, skip=()):
    """keys — имена цветов, которые должны быть в файле темы (обычно профиль версии far2l);
    skip — части, пропущенные при установке: icons, colorer, palette, highlight."""
    results = []

    def check(ok, msg):
        results.append(ok)
        print(("[ok] " if ok else "[FAIL] ") + msg)

    def note(msg):
        print("[!] " + msg)

    check(os.path.isdir(cfg), f"каталог настроек: {cfg}")
    targets = color_targets(profile)
    files = []
    if "theme" in targets and (profile is None or profile["uses_themes"]):
        files.append(("тема", theme_file(cfg)))
    if "legacy" in targets:
        files.append(("settings/farcolors.ini", legacy_file(cfg)))
    for label, path in files:
        have = Ini(path).items("farcolors")
        missing = sorted(set(keys) - set(have))
        check(bool(have) and not missing, f"цвета ({label}): {len(have)}"
              + (f", нет: {', '.join(missing)}" if missing else ", все нужные на месте"))
        wrong = sorted((k for k in have if have[k] != colors.expr(*colors.color_for(k)[:2])),
                       key=lambda k: (not k.startswith("Panel.Info.Tot"), k))  # строка итога — первой
        check(not wrong, f"цвета ({label}) совпадают с far2l_theme/colors.py"
              + (f" — отличаются: {', '.join(wrong[:8])}{' …' if len(wrong) > 8 else ''}" if wrong else ""))
    cur = Ini(os.path.join(cfg, "settings", "colors.ini")).items("Colors")
    if profile is None or profile["uses_themes"]:
        check(cur.get("CurrentTheme") == THEME_NAME and cur.get("CurrentThemeIsSystemWide") == "0",
              f"текущая тема в colors.ini: «{cur.get('CurrentTheme', '')}»")
    pal = os.path.join(cfg, "palette.ini")
    if "palette" in skip:
        print("[-] palette.ini: пропущено (--skip-palette)")
    else:
        with open(pal, encoding="utf-8") if os.path.isfile(pal) else open(os.devnull) as fh:
            check(fh.read() == colors.palette_text(), "palette.ini совпадает с far2l_theme/colors.py")
    ini = Ini(os.path.join(cfg, "settings", "colors.ini"))
    groups = highlight_groups(ini)
    if "highlight" in skip:
        print("[-] раскраска файлов: пропущено (--skip-highlight)")
    else:
        plan = highlight_plan(ini)
        check(bool(groups) and not plan, f"раскраска файлов: {len(groups)} групп"
              + (f", не доделано: {', '.join(plan)}" if plan else ""))
    cdir = os.path.join(cfg, "plugins", "colorer")
    if "colorer" in skip or "$" in cdir:
        print("[-] Colorer: пропущено" + (" (--skip-colorer)" if "colorer" in skip else " («$» в пути к настройкам)"))
    else:
        _verify_colorer(cdir, check, note)
    if "icons" not in skip and sys.platform != "darwin":
        _verify_icons(dhome, check)
    ok = all(results)
    print("ИТОГ: " + ("всё установлено" if ok else "есть проблемы (см. FAIL)"))
    return ok


def _verify_colorer(cdir, check, note):
    cc = Ini(os.path.join(cdir, "config.ini")).items("Settings")
    hrd = os.path.join(cdir, f"{HRD_NAME}.hrd")
    err = check_hrd(hrd) if os.path.isfile(hrd) else "файла нет"
    check(err is None, f"Colorer: схема {hrd}" + (f" — {err}" if err else ""))
    uh = cc.get("UserHrdPath", "")
    err = check_hrd_sets(expand_path(uh), hrd) if uh else "UserHrdPath не задан"
    check(err is None, f"Colorer: UserHrdPath={uh or '-'}" + (f" — {err}" if err else ""))
    check(cc.get("HrdNameTm") == HRD_NAME and cc.get("TrueMod", "1") == "1",
          f"Colorer: HrdNameTm={cc.get('HrdNameTm')}, TrueMod={cc.get('TrueMod', '1 (по умолчанию)')}")
    if cc.get("Enabled", "1") == "0":
        note("Colorer выключен (Enabled=0): подсветки в редакторе не будет. Включить: F11 → Colorer, "
             "или python3 install.py --enable-colorer")
    if os.path.isfile(hrd):
        with open(os.path.join(ROOT, "theme", f"{HRD_NAME}.hrd"), encoding="utf-8") as a, open(hrd, encoding="utf-8") as b:
            check(a.read() == b.read(), "Colorer: схема совпадает с theme/graphite.hrd")


def _verify_icons(dhome, check):
    for desktop_id, (icon, svg) in DESKTOP_ICONS.items():
        p = os.path.join(dhome, "applications", desktop_id)
        if not os.path.isfile(p) and not desktop_source(desktop_id, dhome):
            print(f"[-] {desktop_id}: в системе нет — иконка не нужна")
            continue
        svg_ok = os.path.isfile(os.path.join(dhome, "icons", "hicolor", "scalable", "apps", svg))
        icon_line = ""
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                icon_line = next((l for l in fh.read().split("\n") if l.startswith("Icon=")), "")
        check(svg_ok and icon_line == f"Icon={icon}", f"иконка {desktop_id}: {icon_line or 'нет переопределения'}")
