#!/usr/bin/env python3
"""Установщик тёмной графитовой темы «GNOME Graphite» для far2l.

Один установщик для всех поддерживаемых сред. Версию far2l он определяет сам (по `far2l -h`)
и берёт из profiles/ правила этой версии: куда писать цвета, какие имена цветов нужны.
Цвета — в far2l_theme/colors.py, общие файлы темы — в theme/ и icons/.

Команды:
  python3 install.py                  установить тему (с резервной копией настроек)
  python3 install.py --detect         показать, что найдено (версия, профиль, каталоги), ничего не меняя
  python3 install.py --verify         проверить, что всё установлено
  python3 install.py --restore FILE   откатиться из резервной копии
  python3 install.py --export DIR     сгенерировать готовые файлы темы (каталог theme/)

Перед установкой far2l должен быть закрыт: при сохранении настроек он перезаписал бы изменения.
"""
import argparse
import os
import shutil
import sys

sys.dont_write_bytecode = True  # не оставлять __pycache__ в репозитории
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from far2l_theme import colors, detect, steps  # noqa: E402
from far2l_theme.backup import backup, list_backups, restore  # noqa: E402
from far2l_theme.ini import Ini, write_atomic  # noqa: E402
from far2l_theme.verify import verify  # noqa: E402


def log(level, msg):
    print(f"[{level}] {msg}")


def print_detect(info):
    p = info["profile"]
    print(f"far2l: {info['exe'] or 'не найден в PATH'}")
    print(f"версия: {info['version'] or 'не определена'}")
    print(f"профиль: {p['name'] if p else 'нет'} ({info['profile_reason']})"
          + (f" — {p['summary']}" if p else ""))
    print(f"графический модуль: {info['gui_module'] or 'не найден (только терминальный режим)'}")
    print(f"каталог настроек: {info['config_dir']}")
    if info["session"] or info["desktop"]:
        print(f"сеанс: {info['desktop'] or '?'} / {info['session'] or '?'}")


def main():
    ap = argparse.ArgumentParser(description="Тёмная графитовая тема GNOME Graphite для far2l")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="проверить установку")
    mode.add_argument("--detect", action="store_true", help="показать найденную версию far2l и профиль")
    mode.add_argument("--restore", metavar="BACKUP", help="откатиться из резервной копии .tar.gz")
    mode.add_argument("--export", metavar="DIR", help="записать готовые farcolors.ini и palette.ini в DIR")
    ap.add_argument("--config-dir", default=None, help="каталог настроек far2l (по умолчанию как у far2l)")
    ap.add_argument("--data-home", default=None, help="куда ставить иконки (по умолчанию $XDG_DATA_HOME или ~/.local/share)")
    ap.add_argument("--profile", default=None, help="профиль версии far2l вместо автоопределения (имя каталога в profiles/)")
    ap.add_argument("--skip-icons", action="store_true", help="не трогать иконки")
    ap.add_argument("--skip-colorer", action="store_true", help="не трогать подсветку синтаксиса")
    ap.add_argument("--skip-palette", action="store_true", help="не трогать palette.ini")
    ap.add_argument("--skip-highlight", action="store_true", help="не трогать раскраску файлов")
    ap.add_argument("--enable-colorer", action="store_true", help="включить Colorer, если он выключен (Enabled=0)")
    ap.add_argument("--no-bootstrap", action="store_true", help="не запускать far2l для создания настроек")
    ap.add_argument("--no-backup", action="store_true", help="не делать резервную копию")
    ap.add_argument("--force", action="store_true", help="продолжить, даже если запущен far2l")
    a = ap.parse_args()

    cfg = os.path.abspath(os.path.expanduser(a.config_dir)) if a.config_dir else detect.default_config_dir()
    dhome = os.path.abspath(os.path.expanduser(a.data_home)) if a.data_home else detect.data_home()
    profiles = detect.load_profiles()

    if a.export:
        keys = sorted(detect.all_known_keys(profiles))
        text, guessed = colors.farcolors_text(keys)
        write_atomic(os.path.join(a.export, "farcolors.ini"), text, mode=0o644)
        write_atomic(os.path.join(a.export, "palette.ini"), colors.palette_text(), mode=0o644)
        log("ok", f"записано в {a.export}: {len(keys)} цветов"
                  + (f"; подобрано по названию: {', '.join(guessed)}" if guessed else ""))
        return 0

    info = detect.describe(cfg, profiles, a.profile)
    profile = info["profile"]
    if a.detect:
        print_detect(info)
        return 0
    if a.verify:
        if not info["supported"] and not a.profile:
            print(f"[FAIL] {info['version']}: {info['profile_reason']} — тема на эту сборку не встанет")
            print("ИТОГ: есть проблемы (см. FAIL)")
            return 1
        keys = profile["keys"] if profile else sorted(detect.all_known_keys(profiles))
        skip = {k for k in ("icons", "colorer", "palette", "highlight") if getattr(a, f"skip_{k}")}
        return 0 if verify(cfg, dhome, profile, keys, skip) else 1

    running = detect.far2l_processes()
    if running and not a.force:
        print("[STOP] far2l запущен (процессы: " + ", ".join(f"{n} {p}" for p, n in running) + ").\n"
              "       Закройте его (F10) и повторите: при сохранении настроек он перезаписал бы изменения.\n"
              "       Если окна far2l не видно, он мог остаться в фоне после закрытия терминала:\n"
              "       запустите far2l в терминале — он предложит вернуть фоновый сеанс — и выйдите по F10.\n"
              "       Если запущенный far2l работает с другим каталогом настроек, добавьте --force.")
        return 2
    if a.restore:
        restore(a.restore, log, a.data_home and dhome)
        return 0
    if not info["supported"] and not a.profile:
        print(f"[STOP] {info['version']}: {info['profile_reason']}.\n"
              "       Обновите far2l (см. environments/*/README.md) или, если уверены, укажите --profile.")
        return 3

    print_detect(info)
    if profile is None:
        log("!", "профиль версии не выбран — цвета будут записаны и в тему, и в settings/farcolors.ini")
    elif profile.get("note"):
        log("!", profile["note"])
    if not a.no_backup:
        backup(cfg, dhome, log, steps.theme_present(cfg))
    if not steps.highlight_groups(Ini(os.path.join(cfg, "settings", "colors.ini"))) and not a.no_bootstrap:
        if detect.far2l_env(cfg) is None:
            log("!", "far2l нельзя запустить с этим каталогом настроек: подходят каталог по умолчанию,\n"
                     "    ПУТЬ/.config (far2l -u ПУТЬ) и ~/.config/far2l/custom/ИМЯ (far2l -u ИМЯ).\n"
                     "    Группы раскраски файлов не созданы; цвет под курсором не настроен.")
        elif not (shutil.which("tmux") and info["exe"]):
            log("!", "не удалось автоматически создать настройки far2l: нужны tmux и far2l в PATH.\n"
                     "    Запустите far2l один раз, выйдите по F10 и повторите установку.")
        else:
            log("..", "первый запуск far2l в tmux, чтобы он создал настройки по умолчанию")
            if steps.bootstrap(cfg):
                log("ok", "far2l создал настройки по умолчанию")
            else:
                log("!", "первый запуск far2l в tmux не удался. Запустите far2l один раз, выйдите по F10\n"
                         "    и повторите установку.")
    steps.step_colors(cfg, profile, detect.color_keys(cfg, profiles, info["exe"]), log)
    if not a.skip_palette:
        steps.step_palette(cfg, log)
    if not a.skip_highlight:
        steps.step_highlight(cfg, log)
    if not a.skip_colorer:
        steps.step_colorer(cfg, log, enable=a.enable_colorer)
    if not a.skip_icons:
        steps.step_icons(dhome, log)
    clean = [p for p, had in list_backups(cfg) if not had]
    if clean:  # самая свежая копия без темы — состояние прямо перед последней установкой на чистые настройки
        log("ok", f"откат к виду до темы: python3 install.py --restore {clean[-1]}")
    else:
        log("!", "резервной копии без темы нет (тему ставили раньше без копии или с --no-backup)")
    print("Готово. Запустите far2l. Проверка: python3 install.py --verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
