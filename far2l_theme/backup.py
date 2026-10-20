"""Резервная копия настроек far2l и пользовательских иконок, откат из неё.

Что учитывается:
  * каталог настроек может быть ссылкой (dotfiles): копируется его содержимое, откат идёт в цель ссылки;
  * внутри него тоже бывают ссылки — на файлы и на подкаталоги (GNU stow). Установщик пишет в их цели,
    поэтому в копию кладётся и содержимое целей (_linked/, _linkeddir/), а откат возвращает его;
  * профили far2l -u ИМЯ (custom/ИМЯ) — отдельные профили: копия и откат основного профиля их не трогают;
  * откат сначала полностью распаковывает копию во временный каталог и только потом меняет каталоги местами.
"""
import datetime
import io
import json
import os
import shutil
import tarfile
import tempfile

from .ini import write_atomic
from .steps import DESKTOP_ICONS, THEME_NAME, is_ours

MANIFEST = "_far2l_dark_theme_backup.json"


def _icon_paths(dhome):
    out = {}
    for desktop_id, (_icon, svg) in DESKTOP_ICONS.items():
        out[f"_desktop/{desktop_id}"] = os.path.join(dhome, "applications", desktop_id)
        out[f"_icons/{svg}"] = os.path.join(dhome, "icons", "hicolor", "scalable", "apps", svg)
    return out


def _far2l_root_of_custom(cfg):
    """Корень far2l, если cfg — профиль `far2l -u ИМЯ` (…/far2l/custom/ИМЯ)."""
    parent = os.path.dirname(cfg)
    if os.path.basename(parent) == "custom" and os.path.basename(os.path.dirname(parent)) == "far2l":
        return os.path.dirname(parent)
    return None


def _base(cfg):
    base = cfg.rstrip("/")
    root = _far2l_root_of_custom(base)
    # Копию профиля custom/ИМЯ кладём рядом с корнем far2l, а не внутрь основного профиля.
    return f"{root}-custom-{os.path.basename(base)}" if root else base


def backup_path(cfg, ts):
    base = _base(cfg)
    path, n = f"{base}-backup-{ts}.tar.gz", 1
    while os.path.exists(path):
        n += 1
        path = f"{base}-backup-{ts}-{n}.tar.gz"
    return path


def list_backups(cfg):
    """Пригодные копии этого каталога настроек, от старых к новым: [(путь, была_ли_тема)]."""
    prefix = _base(cfg) + "-backup-"
    d = os.path.dirname(prefix)
    found = []
    if not os.path.isdir(d):
        return found
    for name in os.listdir(d):
        p = os.path.join(d, name)
        if not (p.startswith(prefix) and name.endswith(".tar.gz")):
            continue
        try:
            with tarfile.open(p, "r:gz") as tar:
                meta = json.load(tar.extractfile(MANIFEST))
                arc = meta.get("arcname", "")
                if meta.get("config_existed"):
                    top = tar.getmember(arc)
                    if top.issym():  # копия прежней версии каталога-ссылки: в ней нет самих настроек
                        continue
                had = meta.get("theme_installed")
                if had is None:  # копии прежних версий установщика: смотрим, была ли в них тема
                    had = any(n.startswith(f"{arc}/settings/themes/{THEME_NAME}/") for n in tar.getnames())
        except Exception:  # недописанная или чужая копия — просто пропускаем
            continue
        found.append((os.path.getmtime(p), p, had))
    return [(p, had) for _, p, had in sorted(found)]


def backup(cfg, dhome, log, theme_installed):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = backup_path(cfg, ts)
    arc = os.path.basename(cfg.rstrip("/"))
    exists = os.path.isdir(cfg)
    real = os.path.realpath(cfg) if exists else cfg
    excluded = [] if _far2l_root_of_custom(cfg.rstrip("/")) else ["custom"]

    def in_custom(rel):
        return excluded and (rel == "custom" or rel.startswith("custom" + os.sep))

    def skip_custom(ti):
        rel = ti.name[len(arc):].lstrip("/")
        return None if in_custom(rel) else ti

    files, linked, linked_dirs = {}, {}, {}
    seen = set()

    def collect_links(tar, top, prefix):
        """Ссылки внутри top: на файлы — в _linked/, на каталоги — в _linkeddir/ (и внутри них тоже)."""
        if os.path.realpath(top) in seen:  # защита от петель из ссылок
            return
        seen.add(os.path.realpath(top))
        for dirpath, dirnames, filenames in os.walk(top):
            rel_dir = os.path.normpath(os.path.join(prefix, os.path.relpath(dirpath, top)))
            if in_custom(rel_dir):
                dirnames[:] = []
                continue
            for d in list(dirnames):
                full = os.path.join(dirpath, d)
                rel = os.path.normpath(os.path.join(rel_dir, d))
                if os.path.islink(full) and os.path.isdir(full) and not in_custom(rel):
                    target = os.path.realpath(full)
                    tar.add(target, arcname=f"_linkeddir/{rel}")
                    linked_dirs[rel] = target
                    collect_links(tar, target, rel)
            for f in filenames:
                full = os.path.join(dirpath, f)
                if os.path.islink(full) and os.path.isfile(full):
                    rel = os.path.normpath(os.path.join(rel_dir, f))
                    tar.add(os.path.realpath(full), arcname=f"_linked/{rel}", recursive=False)
                    linked[rel] = os.path.realpath(full)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".far2l-backup-", suffix=".tmp", dir=os.path.dirname(path))
    os.close(fd)
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            if exists:
                tar.add(real, arcname=arc, filter=skip_custom)
                collect_links(tar, real, "")
            for name, p in _icon_paths(dhome).items():
                if os.path.lexists(p):
                    tar.add(p, arcname=name)
                    files[name] = {"path": p}
            data = json.dumps({"version": 3, "config_dir": cfg, "config_real": real, "arcname": arc,
                               "config_existed": exists, "excluded": excluded, "linked": linked,
                               "linked_dirs": linked_dirs, "data_home": dhome, "files": files,
                               "theme_installed": theme_installed}, ensure_ascii=False, indent=1).encode()
            info = tarfile.TarInfo(MANIFEST)
            info.size = len(data)
            info.mtime = int(datetime.datetime.now().timestamp())
            tar.addfile(info, io.BytesIO(data))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)  # копия появляется под своим именем только целиком
    except OSError as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise SystemExit(f"[STOP] резервная копия не создана: {e}\n"
                         f"       Часто это файлы от запуска far2l через sudo: sudo chown -R $USER {real}\n"
                         "       Ничего не изменено.")
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    log("ok", f"резервная копия: {path}" + (" (тема уже была установлена)" if theme_installed else ""))
    return path


def _old_files(meta, dhome):
    """Списки файлов из копий прежних версий установщика."""
    files = {f"_desktop/{d}": {"path": os.path.join(dhome, "applications", d)} for d in meta.get("desktop_files", [])}
    files.update({f"_icons/{s}": {"path": os.path.join(dhome, "icons", "hicolor", "scalable", "apps", s)}
                  for s in meta.get("icon_files", [])})
    return files


def _extract_dir(tar, prefix, parent, kwargs):
    """Распаковать члены архива prefix/… во временный каталог рядом с parent; вернуть (каталог, tmp)."""
    os.makedirs(parent, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".far2l-restore-", dir=parent)
    try:
        members = [m for m in tar.getmembers() if m.name == prefix or m.name.startswith(prefix + "/")]
        tar.extractall(tmp, members=members, **kwargs)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return os.path.join(tmp, prefix), tmp


def _aside_name(target, ts):
    aside, n = f"{target}.replaced-{ts}", 1
    while os.path.lexists(aside):
        n += 1
        aside = f"{target}.replaced-{ts}-{n}"
    return aside


def _swap_in(new, tmp, target, ts):
    """Отложить target (если есть) и поставить new на его место."""
    aside = None
    try:
        if os.path.isdir(target):
            aside = _aside_name(target, ts)
            os.rename(target, aside)
        os.rename(new, target)
    except BaseException:
        if aside and not os.path.exists(target):
            os.rename(aside, target)  # вернуть как было
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return aside


def restore(path, log, dhome_override=None):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    kwargs = {"filter": "tar"} if hasattr(tarfile, "tar_filter") else {}
    with tarfile.open(path, "r:gz") as tar:
        meta = json.load(tar.extractfile(MANIFEST))
        cfg, arc = meta["config_dir"], meta["arcname"]
        dhome = dhome_override or meta["data_home"]
        files = meta.get("files")
        if files is None:
            files = _old_files(meta, dhome)
        elif files and isinstance(next(iter(files.values())), str):
            files = {k: {"path": v} for k, v in files.items()}
        if meta["config_existed"] and tar.getmember(arc).issym():
            raise SystemExit("[STOP] в этой копии вместо настроек только ссылка на каталог (так сохраняла "
                             "первая версия установщика) — откат из неё невозможен, ничего не изменено.")
        # Каталог-ссылка остаётся ссылкой: меняется содержимое её цели.
        target = os.path.realpath(cfg) if os.path.lexists(cfg) else meta.get("config_real", cfg)
        keep_custom = "custom" in meta.get("excluded", []) or not _far2l_root_of_custom(cfg.rstrip("/"))

        if meta["config_existed"]:
            new, tmp = _extract_dir(tar, arc, os.path.dirname(target), kwargs)  # сначала распаковать целиком
            aside = _swap_in(new, tmp, target, ts)
            log("ok", f"настройки восстановлены: {target}")
        else:
            aside = None
            if os.path.isdir(target):
                aside = _aside_name(target, ts)
                os.rename(target, aside)
        if aside:
            log("ok", f"прежние текущие настройки отложены в {aside}")
            if keep_custom and os.path.isdir(os.path.join(aside, "custom")) \
                    and not os.path.exists(os.path.join(target, "custom")):
                if not os.path.isdir(target):
                    os.makedirs(target)
                    os.chmod(target, os.stat(aside).st_mode & 0o777)  # как у far2l (0700)
                os.rename(os.path.join(aside, "custom"), os.path.join(target, "custom"))
                log("ok", "профили custom/ (far2l -u ИМЯ) оставлены как были")

        for rel, real in meta.get("linked_dirs", {}).items():
            try:
                new, tmp = _extract_dir(tar, f"_linkeddir/{rel}", os.path.dirname(real), kwargs)
                moved = _swap_in(new, tmp, real, ts)
                log("ok", f"каталог по ссылке {rel} восстановлен: {real}" + (f" (прежний — {moved})" if moved else ""))
            except (OSError, KeyError, tarfile.TarError) as e:
                log("!", f"не восстановлен каталог по ссылке {rel} → {real}: {e}")
        for rel, real in meta.get("linked", {}).items():
            try:
                write_atomic(real, tar.extractfile(f"_linked/{rel}").read())
            except (OSError, KeyError) as e:
                log("!", f"не восстановлен файл по ссылке {rel} → {real}: {e}")

        # Наши иконки и .desktop убираем, затем возвращаем то, что было в копии.
        for name, p in _icon_paths(dhome).items():
            if not os.path.lexists(p) or os.path.islink(p) or name in files:
                continue  # ссылки ставили не мы
            if name.startswith("_desktop/"):
                with open(p, encoding="utf-8") as fh:
                    if not is_ours(fh.read()):
                        continue
            os.remove(p)
        for name, info in files.items():
            target_p = _icon_paths(dhome).get(name) or info["path"]
            try:
                m = tar.getmember(name)
                os.makedirs(os.path.dirname(target_p), exist_ok=True)
                if m.issym():
                    if os.path.lexists(target_p):
                        os.remove(target_p)
                    os.symlink(m.linkname, target_p)
                else:
                    write_atomic(target_p, tar.extractfile(m).read(), mode=m.mode & 0o777, follow_symlinks=False)
            except (OSError, KeyError) as e:
                log("!", f"не восстановлен {target_p}: {e}")
    log("ok", "иконки и .desktop-файлы — как на момент резервной копии")
