"""Модульные тесты (far2l не нужен): python3 -m unittest discover -s tests"""
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from far2l_theme import backup, colors, detect, steps  # noqa: E402
from far2l_theme.ini import Ini, write_atomic  # noqa: E402

# Штатные группы far2l 2.6.5 (hilight.cpp, StdHighlightData) в том виде, как они попадают в colors.ini.
DEFAULT_265 = """[Colors/Highlight]
Initialized=1

[Colors/Highlight/Group9]
Name=Hidden files
NormalColor=0x13
NormalColorMask=0xfffffffd0f
CursorColor=0x38
CursorColorMask=0xfffffffd0f

[Colors/Highlight/Group12]
Name=Parent dir
NormalColor=0x0
NormalColorMask=0xfffffffd0f
CursorColor=0x0
CursorColorMask=0xfffffffd0f

[Colors/Highlight/Group16]
Name=Source
NormalColor=0xffbcac0112
NormalColorMask=0xfffffffd0f
CursorColor=0x8f0c000132
CursorColorMask=0xfffffffd0f
"""

# Группа из far2l до 2.6.2: без масок, непрозрачный синий фон (индекс 1).
LEGACY = """[Colors/Highlight/Group0]
Name=Old dirs
NormalColor=0x1f
CursorColor=0x3f
"""


class Tmp(unittest.TestCase):
    def tmpdir(self):
        d = tempfile.mkdtemp(prefix="far2l-theme-test-")
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def tmp_ini(self, text):
        p = os.path.join(self.tmpdir(), "colors.ini")
        with open(p, "w") as fh:
            fh.write(text)
        return Ini(p)


def rd(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def wr(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def quiet(fn, *a, **kw):
    msgs = []
    with redirect_stdout(io.StringIO()):
        fn(*a, log=lambda lvl, m: msgs.append((lvl, m)), **kw)
    return msgs


class IniTest(Tmp):
    def test_last_wins_and_merge(self):
        ini = self.tmp_ini("[S]\na=1\n; a=comment\n[T]\nx=1\n[S]\na=2\nb=3\n")
        self.assertEqual(ini.items("S"), {"a": "2", "b": "3"})

    def test_set_updates_every_copy_and_appends(self):
        ini = self.tmp_ini("[S]\na=1\n[S]\na=2\n")
        ini.set("S", {"a": "9", "c": "7"})
        self.assertEqual(ini.items("S"), {"a": "9", "c": "7"})
        self.assertEqual(ini.text().count("a=9"), 2)

    def test_new_section(self):
        ini = self.tmp_ini("")
        ini.set("Colors", {"CurrentTheme": "X"})
        ini.save()
        self.assertEqual(Ini(ini.path).get("Colors", "CurrentTheme"), "X")

    def test_write_through_symlink(self):
        d = self.tmpdir()
        real = os.path.join(d, "dotfiles.ini")
        wr(real, "[S]\na=1\n")
        link = os.path.join(d, "colors.ini")
        os.symlink(real, link)
        write_atomic(link, "[S]\na=2\n")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(rd(real), "[S]\na=2\n")
        write_atomic(link, "x", follow_symlinks=False)
        self.assertFalse(os.path.islink(link))


class ColorsTest(unittest.TestCase):
    def setUp(self):
        self.profiles = detect.load_profiles()

    def test_every_known_key_has_explicit_rule(self):
        guessed = [k for k in detect.all_known_keys(self.profiles) if not colors.color_for(k)[2]]
        self.assertEqual(guessed, [])

    def test_265_total_alias(self):
        self.assertEqual(colors.color_for("Panel.Info.Tota"), colors.color_for("Panel.Info.Total"))

    def test_index_fallback_readable_in_terminal(self):
        # Без TrueColor (--norgb, TERM=screen* в 2.8) far2l рисует индексами через одну палитру терминала.
        for k in detect.all_known_keys(self.profiles):
            bg, fg, _ = colors.color_for(k)
            b, f = colors.index_pair(bg, fg)
            self.assertGreaterEqual(colors.contrast(colors.TTY_PALETTE[f], colors.TTY_PALETTE[b]), 3.0, k)

    def test_cursor_stands_out_without_truecolor(self):
        panel, _ = colors.index_pair(colors.BG, colors.TEXT)
        cursor, _ = colors.index_pair(colors.CURSOR, colors.BRIGHT)
        self.assertNotEqual(panel, cursor)
        fb = colors.TTY_PALETTE[colors.CURSOR_FALLBACK_FG]
        self.assertGreaterEqual(colors.contrast(fb, colors.TTY_PALETTE[cursor]), 4.5)

    def test_expr_format(self):
        e = colors.expr("#1d1d20", "#deddda")
        self.assertRegex(e, r"^background:#1d1d20 foreground:#deddda, B_[A-Z]+ \| F_[A-Z]+; back_rgb\(29, 29, 32\)")

    def test_prebuilt_theme_is_current(self):
        keys = sorted(detect.all_known_keys(self.profiles))
        with open(os.path.join(detect.ROOT, "theme", "farcolors.ini"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), colors.farcolors_text(keys)[0], "запустите: python3 install.py --export theme")
        with open(os.path.join(detect.ROOT, "theme", "palette.ini"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), colors.palette_text())


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.profiles = detect.load_profiles()

    def pick(self, version, markers):
        return detect.pick_profile(version, self.profiles, markers=markers)

    def test_profiles(self):
        names = {p["name"]: p for p in self.profiles}
        self.assertEqual(len(names["far2l-2.6"]["keys"]), 147)
        self.assertEqual(len(names["far2l-2.8"]["keys"]), 160)
        self.assertIn("Panel.Info.Tota", names["far2l-2.6"]["keys"])

    def test_by_version_and_capabilities(self):
        both = {"settings/farcolors.ini", "settings/themes/"}
        self.assertEqual(self.pick((2, 6, 5), {"settings/farcolors.ini"})[0]["name"], "far2l-2.6")
        self.assertEqual(self.pick((2, 8, 0), both)[0]["name"], "far2l-2.8")
        self.assertEqual(self.pick((2, 9, 1), both)[0]["name"], "far2l-2.8")
        self.assertEqual(self.pick((2, 6, 4), {"settings/farcolors.ini"})[0]["name"], "far2l-2.6")  # снимок 2.6.4 из git
        p, why, ok = self.pick((2, 6, 4), set())  # 2.6.4 без farcolors.ini — цвета в другом месте
        self.assertIsNone(p)
        self.assertFalse(ok)
        p, _, ok = self.pick((2, 5, 0), set())
        self.assertIsNone(p)
        self.assertFalse(ok)
        p, _, ok = self.pick((2, 6, 1), None)  # обёртка-скрипт: возможности неизвестны, но 2.6.1 точно стара
        self.assertIsNone(p)
        self.assertFalse(ok)
        p, _, ok = self.pick(None, None)
        self.assertIsNone(p)
        self.assertTrue(ok)
        self.assertEqual(self.pick((2, 6, 5), None)[0]["name"], "far2l-2.6")  # бинарник не прочитать


class DetectBinaryTest(Tmp):
    def test_wrapper_script_is_unknown(self):
        p = os.path.join(self.tmpdir(), "far2l")
        wr(p, "#!/bin/sh\nexec /opt/far2l/bin/far2l \"$@\"\n")
        self.assertIsNone(detect.binary_markers(p, ["settings/farcolors.ini"]))

    def test_elf_markers(self):
        p = os.path.join(self.tmpdir(), "far2l")
        with open(p, "wb") as fh:
            fh.write(b"\x7fELF" + b"\0" * (1 << 20) + b"settings/farcolors.ini\0FAR2L Version: %s\0")
        self.assertEqual(detect.binary_markers(p, ["settings/farcolors.ini", "settings/themes/"]),
                         {"settings/farcolors.ini"})

    def test_elf_launcher_is_unknown(self):  # AppImage, скомпилированная обёртка: в них нет far2l
        p = os.path.join(self.tmpdir(), "far2l")
        with open(p, "wb") as fh:
            fh.write(b"\x7fELF" + b"\0" * 4096)
        self.assertIsNone(detect.binary_markers(p, ["settings/farcolors.ini"]))


class HighlightTest(Tmp):
    def apply(self, ini):
        for sec, ch in steps.highlight_plan(ini).items():
            ini.set(sec, ch)

    def test_defaults(self):
        ini = self.tmp_ini(DEFAULT_265)
        plan = steps.highlight_plan(ini)
        # Скрытые файлы: индекс 3 → RGB из палитры темы + запасной белый индекс для режима без TrueColor.
        hidden = steps.cursor_color(0x13)
        self.assertEqual(hidden & 0xF, colors.CURSOR_FALLBACK_FG)
        self.assertEqual((hidden >> 16) & 0xFFFFFF, steps._bgr(colors.PALETTE_FG[3]))
        self.assertEqual(plan["Colors/Highlight/Group9"], {"CursorColor": hex(hidden), "CursorColorMask": "0xfffffffd0f"})
        self.assertEqual(int(plan["Colors/Highlight/Group16"]["CursorColor"], 16) >> 16, 0xffbcac)
        self.assertNotIn("Colors/Highlight/Group12", plan)  # «наследовать» не трогаем
        self.apply(ini)
        self.assertEqual(steps.highlight_plan(ini), {})  # идемпотентно

    def test_legacy_without_masks(self):
        ini = self.tmp_ini(LEGACY)
        self.apply(ini)
        g = ini.items("Colors/Highlight/Group0")
        self.assertEqual(int(g["NormalColorMask"], 16) & steps.BG_BITS, 0)  # синий фон убран
        self.assertEqual(int(g["CursorColor"], 16) >> 16, steps._bgr(colors.PALETTE_FG[15]))
        self.assertEqual(steps.highlight_plan(ini), {})

    def test_never_writes_zero_mask(self):
        ini = self.tmp_ini("[Colors/Highlight/Group0]\nNormalColor=0x10\nNormalColorMask=0xf0\n")
        self.assertNotIn("NormalColorMask", steps.highlight_plan(ini).get("Colors/Highlight/Group0", {}))

    def test_cursor_mask_never_has_background(self):
        ini = self.tmp_ini("[Colors/Highlight/Group0]\nNormalColor=0x2a0000000000001f\nNormalColorMask=0xffffffffffffffff\n"
                           "CursorColor=0x3f\nCursorColorMask=0xfffffffd0f\n")
        self.apply(ini)
        g = ini.items("Colors/Highlight/Group0")
        self.assertEqual(int(g["CursorColorMask"], 16) & steps.BG_BITS, 0)
        self.assertEqual(g["NormalColorMask"], "0xffffffffffffffff")  # фон, выбранный пользователем, сохранён

    def test_other_group_families(self):
        ini = self.tmp_ini(DEFAULT_265.replace("Colors/Highlight/Group9", "SortGroups/UpperGroup0"))
        self.assertIn("SortGroups/UpperGroup0", steps.highlight_plan(ini))


class ColorerTest(Tmp):
    def setup_cfg(self, user_hrd_line):
        cfg = os.path.join(self.tmpdir(), "a&b <c>", "far2l")
        cdir = os.path.join(cfg, "plugins", "colorer")
        os.makedirs(cdir)
        with open(os.path.join(cdir, "config.ini"), "w") as fh:
            fh.write(f"[Settings]\n{user_hrd_line}\nEnabled=0\n")
        return cfg, cdir

    def names(self, cdir):
        return [h.get("name") for h in ET.parse(os.path.join(cdir, "user-hrd.xml")).getroot()]

    def test_theme_hrd_valid(self):
        path = os.path.join(detect.ROOT, "theme", "graphite.hrd")
        self.assertIsNone(steps.check_hrd(path))
        text = [a for a in ET.parse(path).getroot() if a.get("name") == "def:Text"][0]
        self.assertEqual(text.get("back").lower(), colors.BG)  # фон редактора = фон темы

    def test_symlinked_scheme_accepted(self):
        d = self.tmpdir()
        real = os.path.join(d, "real.hrd")
        shutil.copyfile(os.path.join(detect.ROOT, "theme", "graphite.hrd"), real)
        link = os.path.join(d, "graphite.hrd")
        os.symlink(real, link)
        sets = os.path.join(d, "user-hrd.xml")
        wr(sets, f'<hrd-sets><hrd class="rgb" name="graphite"><location link="{link}"/></hrd></hrd-sets>')
        self.assertIsNone(steps.check_hrd_sets(sets, link))

    def test_merge_escape_and_rerun(self):
        d = self.tmpdir()
        foreign = os.path.join(d, "mine.xml")
        with open(foreign, "w") as fh:
            fh.write('<hrd-sets><hrd class="rgb" name="mine"><location link="/x/mine.hrd"/></hrd></hrd-sets>')
        with mock.patch.dict(os.environ, {"MYHRD": d}):
            cfg, cdir = self.setup_cfg('UserHrdPath="$MYHRD/mine.xml"')
            msgs = quiet(steps.step_colorer, cfg)
        self.assertIsNone(steps.check_hrd_sets(os.path.join(cdir, "user-hrd.xml"), os.path.join(cdir, "graphite.hrd")))
        self.assertEqual(self.names(cdir), ["graphite", "mine"])
        self.assertTrue(any(lvl == "!" and "Enabled=0" in m for lvl, m in msgs))
        quiet(steps.step_colorer, cfg)  # повторный запуск не теряет схему пользователя
        self.assertEqual(self.names(cdir), ["graphite", "mine"])

    def test_hrd_directory(self):
        d = self.tmpdir()
        with open(os.path.join(d, "my.hrd"), "w") as fh:
            fh.write('<hrd class="rgb" name="my" description="Mine"><assign name="def:Text" fore="#ffffff" back="#101010"/></hrd>')
        cfg, cdir = self.setup_cfg(f"UserHrdPath={d}")
        quiet(steps.step_colorer, cfg)
        self.assertEqual(self.names(cdir), ["graphite", "my"])


class DetectTest(unittest.TestCase):
    def test_config_dir_rules(self):
        with mock.patch.dict(os.environ, {"FARSETTINGS": "/opt/p/", "XDG_CONFIG_HOME": "/x"}):
            self.assertEqual(detect.default_config_dir(), "/opt/p/.config")
        with mock.patch.dict(os.environ, {"FARSETTINGS": "", "XDG_CONFIG_HOME": "/x"}):
            self.assertEqual(detect.default_config_dir(), "/x/far2l")
        with mock.patch.dict(os.environ, {"FARSETTINGS": "work", "XDG_CONFIG_HOME": "/x"}):
            self.assertEqual(detect.default_config_dir(), "/x/far2l/custom/work")
            self.assertEqual(detect.far2l_env("/x/far2l/custom/work")["FARSETTINGS"], "work")
        with mock.patch.dict(os.environ, {"FARSETTINGS": "", "XDG_CONFIG_HOME": "/x"}):
            self.assertEqual(detect.far2l_env("/tmp/s/.config")["FARSETTINGS"], "/tmp/s")
            self.assertIsNone(detect.far2l_env("/tmp/elsewhere"))


class DesktopTest(Tmp):
    def test_set_icon(self):
        t = steps.set_desktop_icon("[Desktop Entry]\nName=far2l\nIcon=far2l\n[Desktop Action x]\nIcon=keep\n", "far2l-graphite")
        self.assertIn("Icon=far2l-graphite", t)
        self.assertIn("Icon=keep", t)
        self.assertTrue(t.startswith(steps.MARKER))
        self.assertTrue(steps.is_ours("[Desktop Entry]\nIcon=far2l-graphite\n"))  # переопределения первой версии

    def test_user_launcher_survives_rerun(self):
        dhome = self.tmpdir()
        sysdir = self.tmpdir()
        os.makedirs(os.path.join(sysdir, "applications"))
        with open(os.path.join(sysdir, "applications", "far2l.desktop"), "w") as fh:
            fh.write("[Desktop Entry]\nName=far2l\nExec=far2l --notty\nIcon=far2l\n")
        os.makedirs(os.path.join(dhome, "applications"))
        user = os.path.join(dhome, "applications", "far2l.desktop")
        with open(user, "w") as fh:
            fh.write("[Desktop Entry]\nName=My far2l\nExec=far2l --custom\nIcon=far2l\n")
        with mock.patch.dict(os.environ, {"XDG_DATA_DIRS": sysdir}), mock.patch.object(steps, "STANDARD_DATA_DIRS", ()):
            quiet(steps.step_icons, dhome)
            quiet(steps.step_icons, dhome)
        text = rd(user)
        self.assertIn("Name=My far2l", text)
        self.assertIn("Icon=far2l-graphite", text)
        self.assertEqual(text.count(steps.MARKER), 1)


class DesktopLegacyTest(Tmp):
    def test_legacy_marker_user_launcher_kept(self):
        dhome, sysdir = self.tmpdir(), self.tmpdir()
        os.makedirs(os.path.join(sysdir, "applications"))
        wr(os.path.join(sysdir, "applications", "far2l.desktop"), "[Desktop Entry]\nName=far2l\nExec=far2l\nIcon=far2l\n")
        os.makedirs(os.path.join(dhome, "applications"))
        user = os.path.join(dhome, "applications", "far2l.desktop")
        # так записывала прошлая версия установщика: метка без источника, правки пользователя внутри
        wr(user, f"{steps.MARKER}\n[Desktop Entry]\nName=My far2l\nExec=far2l --custom\nIcon=far2l-graphite\n")
        with mock.patch.dict(os.environ, {"XDG_DATA_DIRS": sysdir}), mock.patch.object(steps, "STANDARD_DATA_DIRS", ()):
            quiet(steps.step_icons, dhome)
        self.assertIn("Name=My far2l", rd(user))
        self.assertIn("source=user", rd(user))

    def test_override_kept_when_system_dir_not_visible(self):
        dhome = self.tmpdir()
        os.makedirs(os.path.join(dhome, "applications"))
        sysfile = os.path.join(self.tmpdir(), "far2l.desktop")
        wr(sysfile, "[Desktop Entry]\nName=far2l\nIcon=far2l\n")
        user = os.path.join(dhome, "applications", "far2l.desktop")
        wr(user, steps.set_desktop_icon(rd(sysfile), "far2l-graphite", sysfile))
        with mock.patch.dict(os.environ, {"XDG_DATA_DIRS": self.tmpdir()}), \
                mock.patch.object(steps, "STANDARD_DATA_DIRS", ()):
            quiet(steps.step_icons, dhome)
        self.assertTrue(os.path.exists(user))  # источник жив — переопределение не трогаем
        os.remove(sysfile)
        with mock.patch.dict(os.environ, {"XDG_DATA_DIRS": self.tmpdir()}), \
                mock.patch.object(steps, "STANDARD_DATA_DIRS", ()):
            quiet(steps.step_icons, dhome)
        self.assertFalse(os.path.exists(user))  # источник исчез — устаревшее переопределение убрано


class BackupTest(Tmp):
    def test_symlinked_config_and_custom_profiles(self):
        root = self.tmpdir()
        dot = os.path.join(root, "dotfiles", "far2l")
        os.makedirs(os.path.join(dot, "settings"))
        os.makedirs(os.path.join(dot, "custom", "work"))
        wr(os.path.join(dot, "settings", "colors.ini"), "[Colors]\nCurrentTheme=ORIGINAL\n")
        wr(os.path.join(dot, "custom", "work", "marker"), "work profile")
        outside = os.path.join(root, "dotfiles", "palette.ini")
        wr(outside, "original palette")
        os.symlink(outside, os.path.join(dot, "palette.ini"))
        cfg = os.path.join(root, "config", "far2l")
        os.makedirs(os.path.dirname(cfg))
        os.symlink(dot, cfg)
        dhome = self.tmpdir()
        quiet(lambda log: backup.backup(cfg, dhome, log, False))
        # «Установка»: пишем сквозь ссылки, как установщик.
        write_atomic(os.path.join(cfg, "settings", "colors.ini"), "[Colors]\nCurrentTheme=GNOME Graphite\n")
        write_atomic(os.path.join(cfg, "palette.ini"), "theme palette")
        wr(os.path.join(dot, "custom", "work", "marker"), "work profile, newer")
        path = [p for p, _ in backup.list_backups(cfg)][0]
        quiet(lambda log: backup.restore(path, log))
        self.assertTrue(os.path.islink(cfg))  # ссылка на dotfiles осталась
        self.assertIn("ORIGINAL", rd(os.path.join(cfg, "settings", "colors.ini")))
        self.assertTrue(os.path.islink(os.path.join(dot, "palette.ini")))
        self.assertEqual(rd(outside), "original palette")
        self.assertEqual(rd(os.path.join(dot, "custom", "work", "marker")), "work profile, newer")

    def test_symlinked_subdirectory(self):
        root = self.tmpdir()
        cfg = os.path.join(root, "far2l")
        os.makedirs(cfg)
        dot = os.path.join(root, "dotfiles", "settings")
        os.makedirs(dot)
        wr(os.path.join(dot, "colors.ini"), "ORIGINAL")
        os.symlink(dot, os.path.join(cfg, "settings"))
        quiet(lambda log: backup.backup(cfg, self.tmpdir(), log, False))
        write_atomic(os.path.join(cfg, "settings", "colors.ini"), "THEMED")
        write_atomic(os.path.join(cfg, "settings", "farcolors.ini"), "THEMED")
        path = backup.list_backups(cfg)[0][0]
        quiet(lambda log: backup.restore(path, log))
        self.assertTrue(os.path.islink(os.path.join(cfg, "settings")))
        self.assertEqual(rd(os.path.join(dot, "colors.ini")), "ORIGINAL")
        self.assertFalse(os.path.exists(os.path.join(dot, "farcolors.ini")))

    def test_old_symlink_only_backup_refused_and_broken_skipped(self):
        root = self.tmpdir()
        cfg = os.path.join(root, "far2l")
        os.makedirs(os.path.join(root, "dot"))
        os.symlink(os.path.join(root, "dot"), cfg)
        old = backup.backup_path(cfg, "20200101-000000")
        with tarfile.open(old, "w:gz") as tar:  # так сохраняла первая версия: только ссылка
            tar.add(cfg, arcname="far2l")
            data = json.dumps({"config_dir": cfg, "arcname": "far2l", "config_existed": True,
                               "data_home": root, "desktop_files": []}).encode()
            info = tarfile.TarInfo(backup.MANIFEST)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        wr(backup.backup_path(cfg, "20200101-000001"), "not a tar")  # недописанная копия
        self.assertEqual(backup.list_backups(cfg), [])
        with self.assertRaises(SystemExit):
            quiet(lambda log: backup.restore(old, log))
        self.assertTrue(os.path.islink(cfg))

    def test_custom_profiles_survive_restore_of_empty_state(self):
        root = self.tmpdir()
        cfg = os.path.join(root, "far2l")
        quiet(lambda log: backup.backup(cfg, self.tmpdir(), log, False))  # настроек ещё нет
        os.makedirs(os.path.join(cfg, "custom", "work"))
        wr(os.path.join(cfg, "custom", "work", "x"), "work")
        wr(os.path.join(cfg, "palette.ini"), "themed")
        os.chmod(cfg, 0o700)
        quiet(lambda log: backup.restore(backup.list_backups(cfg)[0][0], log))
        self.assertEqual(rd(os.path.join(cfg, "custom", "work", "x")), "work")
        self.assertEqual(os.stat(cfg).st_mode & 0o777, 0o700)
        self.assertFalse(os.path.exists(os.path.join(cfg, "palette.ini")))

    def test_nested_links_and_double_restore(self):
        root = self.tmpdir()
        cfg = os.path.join(root, "far2l")
        os.makedirs(cfg)
        dot, dot2 = os.path.join(root, "dot", "settings"), os.path.join(root, "dot2")
        os.makedirs(dot)
        os.makedirs(dot2)
        wr(os.path.join(dot2, "colors.ini"), "ORIGINAL")
        os.symlink(os.path.join(dot2, "colors.ini"), os.path.join(dot, "colors.ini"))
        os.symlink(dot, os.path.join(cfg, "settings"))
        quiet(lambda log: backup.backup(cfg, self.tmpdir(), log, False))
        write_atomic(os.path.join(cfg, "settings", "colors.ini"), "THEMED")
        path = backup.list_backups(cfg)[0][0]
        quiet(lambda log: backup.restore(path, log))
        quiet(lambda log: backup.restore(path, log))  # второй откат в ту же секунду не падает
        self.assertEqual(rd(os.path.join(dot2, "colors.ini")), "ORIGINAL")
        self.assertTrue(os.path.islink(os.path.join(cfg, "settings", "colors.ini")))

    def test_custom_profile_backup_outside_default_tree(self):
        p = backup.backup_path("/home/u/.config/far2l/custom/work", "TS")
        self.assertEqual(p, "/home/u/.config/far2l-custom-work-backup-TS.tar.gz")

    def test_symlinked_desktop_restored(self):
        cfg = os.path.join(self.tmpdir(), "far2l")
        os.makedirs(cfg)
        dhome = self.tmpdir()
        os.makedirs(os.path.join(dhome, "applications"))
        link = os.path.join(dhome, "applications", "far2l.desktop")
        os.symlink("/usr/share/applications/far2l.desktop", link)
        path = quiet(lambda log: backup.backup(cfg, dhome, log, False)) and [p for p, _ in backup.list_backups(cfg)][0]
        write_atomic(link, "[Desktop Entry]\nIcon=far2l-graphite\n", follow_symlinks=False)
        quiet(lambda log: backup.restore(path, log))
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.readlink(link), "/usr/share/applications/far2l.desktop")
        with tarfile.open(path) as tar:
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")


if __name__ == "__main__":
    unittest.main()
