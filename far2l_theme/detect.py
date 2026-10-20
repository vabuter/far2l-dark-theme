"""Определение окружения: каталог настроек far2l, версия, профиль версии, графический модуль,
запущенные процессы far2l."""
import glob
import json
import os
import pwd
import re
import shlex
import shutil
import subprocess
import sys

from .ini import Ini

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR = os.path.join(ROOT, "profiles")


def home_dir():
    """Домашний каталог так же, как его берёт far2l: сначала passwd, затем $HOME."""
    try:
        h = pwd.getpwuid(os.geteuid()).pw_dir
        if h and os.path.isdir(h):
            return h
    except KeyError:
        pass
    return os.path.expanduser("~")


def default_config_dir():
    """Повторяет логику far2l (utils/src/InMy.cpp): FARSETTINGS, XDG_CONFIG_HOME, ~/.config."""
    fs = os.environ.get("FARSETTINGS", "")
    while len(fs) > 1 and fs.endswith("/"):
        fs = fs[:-1]
    if fs.startswith("/"):
        return os.path.join(fs, ".config")
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = xdg if xdg.startswith("/") else os.path.join(home_dir(), ".config")
    path = os.path.join(base, "far2l")
    return os.path.join(path, "custom", fs) if fs else path


def far2l_env(cfg):
    """Переменные окружения, чтобы far2l запустился именно с каталогом настроек cfg (или None).
    Пользовательские FAR2L_ARGS и перенаправления вывода убираются: запуск должен быть предсказуемым."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("FAR2L_")}
    cfg = os.path.abspath(cfg.rstrip("/"))
    if os.path.realpath(cfg) == os.path.realpath(default_config_dir()):
        return env
    env.pop("FARSETTINGS", None)
    if os.path.basename(cfg) == ".config":
        env["FARSETTINGS"] = os.path.dirname(cfg)
        return env
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = os.path.join(xdg if xdg.startswith("/") else os.path.join(home_dir(), ".config"), "far2l", "custom")
    if os.path.dirname(cfg) == base:
        env["FARSETTINGS"] = os.path.basename(cfg)
        return env
    return None


def far2l_exe():
    exe = shutil.which("far2l")
    return os.path.realpath(exe) if exe else None


def far2l_version(exe=None):
    """('2.6.5', (2, 6, 5)) по первой строке `far2l -h`; (None, None), если не удалось.
    Важно: `far2l --version` в 2.6.x не существует и запускает сам far2l."""
    exe = exe or far2l_exe()
    if not exe:
        return None, None
    try:
        out = subprocess.run([exe, "-h"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                             timeout=20, env={k: v for k, v in os.environ.items() if k != "FAR2L_ARGS"}).stdout
    except (OSError, subprocess.SubprocessError):
        return None, None
    m = re.search(r"FAR2L Version:\s*(\S+)", out)
    if not m:
        return None, None
    nums = re.match(r"(\d+)\.(\d+)\.(\d+)", m.group(1))
    return m.group(1), (tuple(int(x) for x in nums.groups()) if nums else None)


def parse_version(s):
    return tuple(int(x) for x in s.split("."))


def load_profiles():
    profiles = []
    for path in sorted(glob.glob(os.path.join(PROFILES_DIR, "*", "profile.json"))):
        with open(path, encoding="utf-8") as fh:
            p = json.load(fh)
        p["dir"] = os.path.dirname(path)
        with open(os.path.join(p["dir"], p["keys_file"]), encoding="utf-8") as fh:
            p["keys"] = [k.strip() for k in fh if k.strip() and not k.startswith("#")]
        profiles.append(p)
    return profiles


def binary_markers(exe, markers):
    """Какие строки есть в исполняемом файле far2l. По ним видно, что умеет именно эта сборка:
    номер версии у снимков из git один на несколько месяцев разработки. None — файл не прочитать."""
    if not exe:
        return None
    found, tail = set(), b""
    sentinel = "FAR2L Version"  # есть в каждом far2l (вывод -h); нет — значит, это не сам far2l
    want = [m.encode() for m in list(markers) + [sentinel]]
    try:
        with open(exe, "rb") as fh:
            magic = fh.read(4)
            # Обёртка-скрипт (NixOS, ~/bin/far2l, AppImage-лаунчер): что умеет far2l, по ней не понять.
            if magic not in (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
                return None
            fh.seek(0)
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                buf = tail + chunk
                found |= {m.decode() for m in want if m in buf}
                tail = buf[-256:]
    except OSError:
        return None
    if sentinel not in found:  # ELF-обёртка или AppImage: возможности самого far2l неизвестны
        return None
    return found - {sentinel}


def pick_profile(version, profiles, name=None, markers=None):
    """Профиль для far2l: (профиль, пояснение, поддерживается_ли).

    Профиль выбирается по версии и проверяется по строкам в бинарнике (requires в profile.json):
    например, far2l 2.6.0–2.6.4 без settings/farcolors.ini хранят цвета иначе, тема на них не встанет.
    Профиль None и поддерживается=True означает «версия неизвестна» (far2l не найден)."""
    if name:
        for p in profiles:
            if p["name"] == name:
                return p, f"выбран вручную: {name}", True
        raise SystemExit(f"нет профиля {name}; есть: {', '.join(p['name'] for p in profiles)}")
    if version is None:
        return None, "версию far2l определить не удалось", True

    if markers is None and version < (2, 6, 5):
        # Бинарник не прочитать, а 2.6.4 бывает и с settings/farcolors.ini, и без — не рискуем.
        return None, "версию far2l нельзя проверить по бинарнику, а нужна 2.6.5 или новее", False

    def fits(p):
        return markers is None or set(p.get("requires", [])) <= markers

    by_version = [p for p in profiles if parse_version(p["min_version"]) <= version < parse_version(p["max_version"])]
    for p in by_version:
        if fits(p):
            return p, "по версии", True
    capable = [p for p in profiles if fits(p) and parse_version(p["min_version"]) <= version]
    if capable:
        p = max(capable, key=lambda p: parse_version(p["min_version"]))
        return p, "по возможностям сборки", True
    if any(parse_version(p["min_version"]) <= version for p in profiles) or by_version:
        return None, "эта сборка far2l хранит цвета иначе (нет settings/farcolors.ini) — нужна 2.6.5 или новее", False
    return None, "версия старше поддерживаемых — нужна 2.6.5 или новее", False


def all_known_keys(profiles):
    keys = set()
    for p in profiles:
        keys |= set(p["keys"])
    return keys


def system_theme_dirs(exe=None):
    """Каталоги штатных тем far2l (есть начиная с 2.8)."""
    dirs = []
    exe = exe or far2l_exe()
    if exe:
        prefix = os.path.dirname(os.path.dirname(exe))
        dirs.append(os.path.join(prefix, "share", "far2l", "themes"))
    dirs += ["/usr/share/far2l/themes", "/usr/local/share/far2l/themes"]
    seen, out = set(), []
    for d in dirs:
        r = os.path.realpath(d)
        if os.path.isdir(r) and r not in seen:
            seen.add(r)
            out.append(r)
    return out


def color_keys(cfg, profiles, exe=None):
    """Имена цветов для файла темы: все известные версии far2l, штатные темы установленной версии
    и текущие настройки пользователя. Лишние имена far2l игнорирует, недостающее даёт синий/красный цвет."""
    keys = all_known_keys(profiles)
    for d in system_theme_dirs(exe):
        for f in glob.glob(os.path.join(d, "*", "farcolors.ini")):
            keys |= set(Ini(f).items("farcolors"))
    keys |= set(Ini(os.path.join(cfg, "settings", "farcolors.ini")).items("farcolors"))
    keys.discard("")
    return sorted(keys)


def gui_module(exe=None):
    """Путь к графическому модулю far2l (wx), если он установлен."""
    exe = exe or far2l_exe()
    if not exe:
        return None
    d = os.path.dirname(exe)
    cand = [os.path.join(d, "far2l_gui.so")]
    if os.path.basename(d) == "bin":
        cand.insert(0, os.path.join(os.path.dirname(d), "lib", "far2l", "far2l_gui.so"))
    # far2l в PATH может быть обёрткой: тогда ищем модуль в обычных местах установки.
    cand += [os.path.join(p, "far2l_gui.so") for p in
             ("/usr/lib/far2l", "/usr/lib64/far2l", "/usr/local/lib/far2l", "/usr/libexec/far2l")]
    return next((c for c in cand if os.path.isfile(c)), None)


def far2l_processes():
    """Процессы far2l текущего пользователя: [(pid, имя)]. Включает far2ledit и фоновые копии."""
    exe = far2l_exe()
    uid = os.geteuid()
    found = []
    if os.path.isdir("/proc") and sys.platform.startswith("linux"):
        for pid in filter(str.isdigit, os.listdir("/proc")):
            try:
                if os.stat(f"/proc/{pid}").st_uid != uid or int(pid) == os.getpid():
                    continue
                with open(f"/proc/{pid}/comm") as fh:
                    comm = fh.read().strip()
                with open(f"/proc/{pid}/stat") as fh:
                    if fh.read().rsplit(")", 1)[1].split()[0] == "Z":
                        continue  # завершившийся процесс, которого ещё не убрала система
                try:
                    pexe = os.path.realpath(os.readlink(f"/proc/{pid}/exe"))
                except OSError:
                    pexe = ""
            except (OSError, ValueError):
                continue
            if comm in ("far2l", "far2ledit") or (exe and pexe == exe):
                found.append((int(pid), comm))
        return found
    try:
        out = subprocess.run(["pgrep", "-u", str(uid), "-x", "far2l|far2ledit"], capture_output=True, text=True).stdout
        return [(int(p), "far2l") for p in out.split()]
    except FileNotFoundError:
        return []


def data_home():
    xdg = os.environ.get("XDG_DATA_HOME", "")
    return xdg if xdg.startswith("/") else os.path.join(home_dir(), ".local", "share")


def data_dirs():
    return [d for d in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if d]


def describe(cfg, profiles, profile_name=None):
    """Сводка окружения для вывода и для решений установщика."""
    exe = far2l_exe()
    vstr, vtuple = far2l_version(exe)
    wanted = sorted({m for p in profiles for m in p.get("requires", [])})
    markers = binary_markers(exe, wanted)
    profile, why, supported = pick_profile(vtuple, profiles, profile_name, markers)
    return {
        "exe": exe,
        "version": vstr,
        "version_tuple": vtuple,
        "profile": profile,
        "profile_reason": why,
        "supported": supported,
        "markers": markers,
        "gui_module": gui_module(exe),
        "config_dir": cfg,
        "session": os.environ.get("XDG_SESSION_TYPE", ""),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""),
    }


def quote_env(env_changes):
    return " ".join(f"{k}={shlex.quote(v)}" for k, v in env_changes.items())
