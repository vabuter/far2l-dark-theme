# Fedora 44 + GNOME (Wayland) + far2l 2.8

Профиль: [far2l-2.8](../../profiles/far2l-2.8/README.md). На этой машине тема была создана.

## Откуда far2l

В репозиториях Fedora 44 far2l нет. Используется COPR `polter/far2l`:

```bash
sudo dnf copr enable polter/far2l
```

```bash
sudo dnf install far2l
```

## Особенности

- Ярлыков два: `far2l.desktop` и `far2ledit.desktop`, ярлыков «(Terminal)» в этом пакете нет.
- Под Wayland окно far2l имеет app_id `far2l`, GNOME берёт иконку из `far2l.desktop`.
  Если в доке осталась старая иконка — выйти из сеанса и войти снова.
- Тема видна в far2l: F9 → Параметры → Цвета → «Темы пользователя: GNOME Graphite».
- Для снимков в графическом режиме (`tools/snapshot.py`):
  `sudo dnf install xorg-x11-server-Xvfb xdotool ImageMagick python3-pillow`.

## Как проверено

Точная версия пакета закреплена в `Containerfile` и записана в `expect.json`; `tools/e2e.py`
сверяет её с тем, что оказалось в контейнере.

`python3 tools/e2e.py fedora-44-gnome-wayland-far2l-2.8` — контейнер из [Containerfile](Containerfile):
Fedora 44 и far2l из COPR. Тот же набор проверок, что и для Debian. Снимки — в [screenshots/](screenshots/).
Тема создавалась на рабочей машине автора (GNOME, Wayland), там она используется ежедневно.
