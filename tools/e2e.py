#!/usr/bin/env python3
"""Сквозная проверка темы в контейнерах проверенных окружений (environments/*/Containerfile).

Для каждого окружения: собрать образ, убедиться, что в нём та версия far2l и тот профиль,
что указаны в environments/<окружение>/expect.json, на чистом профиле установить тему,
проверить (--verify), снять экраны в графическом и терминальном режиме и проверить на них цвета
(tools/shotcheck.py), проверить повторную установку и откат. Нужен только podman или docker:
всё остальное работает внутри контейнера, настоящие настройки не затрагиваются.

  python3 tools/e2e.py                                   # все окружения
  python3 tools/e2e.py debian-12-gnome-x11-far2l-2.6     # одно окружение
  python3 tools/e2e.py --screenshots                     # при успехе обновить environments/*/screenshots/
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_DIR = os.path.join(ROOT, "environments")
COPY = ["install.py", "far2l_theme", "profiles", "theme", "icons", "tools"]
SCREENS = ("panels", "menu", "dialog", "warning", "editor")


class Engine:
    def __init__(self):
        self.cmd = shutil.which("podman") or shutil.which("docker")
        if not self.cmd:
            sys.exit("нужен podman или docker")

    def run(self, *args, check=True, input=None):
        return subprocess.run([self.cmd, *args], check=check, input=input, capture_output=True)


def repo_tar():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name in COPY:
            tar.add(os.path.join(ROOT, name), arcname=f"repo/{name}",
                    filter=lambda t: None if "__pycache__" in t.name else t)
    return buf.getvalue()


def run_env(eng, env, out_root, screenshots):
    tag = f"far2l-dark-theme-e2e:{env}"
    name = f"far2l-dark-theme-e2e-{env}-{os.getpid()}"
    with open(os.path.join(ENV_DIR, env, "expect.json"), encoding="utf-8") as fh:
        expect = json.load(fh)
    results = []

    def step(label, ok, detail=""):
        results.append((label, ok))
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))

    print(f"== {env}: сборка образа (первый раз — несколько минут)")
    b = eng.run("build", "-q", "-t", tag, "-f", os.path.join(ENV_DIR, env, "Containerfile"),
                os.path.join(ENV_DIR, env), check=False)
    if b.returncode:
        print(b.stderr.decode(errors="replace")[-2000:])
        step("сборка образа", False)
        return results
    eng.run("run", "-d", "--init", "--name", name, tag, "sleep", "infinity")
    try:
        eng.run("exec", "-i", name, "tar", "-x", "-C", "/home/tester", input=repo_tar())

        def sh(script):
            r = eng.run("exec", "-w", "/home/tester/repo", name, "sh", "-c", script, check=False)
            return r.returncode, r.stdout.decode(errors="replace") + r.stderr.decode(errors="replace")

        rc, out = sh(expect["package_query"])
        got = out.strip()
        step(f"пакет far2l {expect['package_version']}", got == expect["package_version"],
             "" if got == expect["package_version"] else f"в образе {got}: окружение изменилось — перепроверьте "
             "и обновите expect.json, README окружения и tested в профиле")
        rc, out = sh("python3 install.py --detect")
        print("\n".join("    " + line for line in out.strip().splitlines()))
        step(f"far2l {expect['version_prefix']}", f"версия: {expect['version_prefix']}" in out)
        step(f"профиль {expect['profile']} выбран сам", f"профиль: {expect['profile']} (по версии)" in out)
        rc, out = sh("python3 install.py")
        step("установка на чистый профиль", rc == 0 and "far2l создал настройки" in out,
             "" if rc == 0 else out.strip().splitlines()[-1])
        rc, out = sh("python3 install.py --verify")
        step("--verify после установки", rc == 0, "" if rc == 0 else "; ".join(l for l in out.splitlines() if "FAIL" in l))
        rc, out = sh("python3 install.py --no-backup && python3 install.py --verify")
        step("повторная установка", rc == 0)

        local = os.path.join(out_root, env)
        os.makedirs(local, exist_ok=True)
        for backend in ("gui", "tty"):
            rc, out = sh(f"rm -rf /tmp/shots-{backend} && python3 tools/snapshot.py --backend {backend} --out /tmp/shots-{backend}")
            step(f"снимки ({backend})", rc == 0, "" if rc == 0 else out.strip().splitlines()[-1])
            if rc:
                continue
            shutil.rmtree(os.path.join(local, backend), ignore_errors=True)  # иначе cp вложит новые снимки в старые
            eng.run("cp", f"{name}:/tmp/shots-{backend}", os.path.join(local, backend))
            rc, out = sh(f"python3 tools/shotcheck.py --backend {backend} --dir /tmp/shots-{backend}")
            for line in out.strip().splitlines():
                verdict, _, rest = line.partition("\t")
                if verdict in ("PASS", "FAIL"):
                    label, _, value = rest.partition("\t")
                    step(f"{backend}: {label}", verdict == "PASS", value)
                elif line.strip():
                    step("проверка цветов", False, line.strip())

        rc, out = sh("B=$(ls ~/.config/far2l-backup-*.tar.gz | head -1); python3 install.py --restore \"$B\" && "
                     "test ! -e ~/.config/far2l && test ! -e ~/.local/share/applications/far2l.desktop")
        step("откат к состоянию до установки", rc == 0, "" if rc == 0 else out.strip()[-300:])
    finally:
        eng.run("rm", "-f", name, check=False)

    gui = os.path.join(out_root, env, "gui")
    if screenshots:
        if all(ok for _, ok in results) and os.path.isdir(gui):
            dst = os.path.join(ENV_DIR, env, "screenshots")
            os.makedirs(dst, exist_ok=True)
            for n in SCREENS:
                shutil.copyfile(os.path.join(gui, f"{n}.png"), os.path.join(dst, f"{n}.png"))
            print(f"  снимки сохранены в {os.path.relpath(dst, ROOT)}")
        else:
            print("  снимки в репозитории НЕ обновлены: есть ошибки")
    return results


def main():
    ap = argparse.ArgumentParser(description="Сквозная проверка темы в контейнерах")
    ap.add_argument("envs", nargs="*", help="окружения (каталоги в environments/), по умолчанию все")
    ap.add_argument("--out", default=None, help="куда сложить снимки (по умолчанию новый временный каталог)")
    ap.add_argument("--screenshots", action="store_true", help="при успехе обновить environments/*/screenshots/")
    a = ap.parse_args()
    envs = a.envs or sorted(d for d in os.listdir(ENV_DIR) if os.path.isfile(os.path.join(ENV_DIR, d, "Containerfile")))
    out_root = a.out or tempfile.mkdtemp(prefix="far2l-dark-theme-e2e-")
    eng = Engine()
    total = {env: run_env(eng, env, out_root, a.screenshots) for env in envs}
    print("\nИТОГ:")
    ok_all = True
    for env, res in total.items():
        bad = [label for label, ok in res if not ok]
        ok_all &= not bad and bool(res)
        print(f"  {env}: " + ("PASS" if res and not bad else f"FAIL ({len(bad)}: {'; '.join(bad)})"))
    print(f"снимки: {out_root}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
