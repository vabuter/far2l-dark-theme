# Debian 12 + GNOME (X11) + far2l 2.6.5

Профиль: [far2l-2.6](../../profiles/far2l-2.6/README.md).

## Откуда far2l

В основном репозитории Debian 12 far2l нет. Версия 2.6.5 есть в `bookworm-backports`,
пакеты разбиты так:

| Пакет | Что в нём |
|---|---|
| `far2l` | программа, плагины, ярлыки `far2l-tty.desktop` и `far2ledit-tty.desktop` («(Terminal)»), иконки |
| `far2l-wx` | графический модуль `/usr/lib/far2l/far2l_gui.so`, ярлыки `far2l.desktop` и `far2ledit.desktop` |

Сначала подключить backports (если ещё не подключены):

```bash
echo 'deb http://deb.debian.org/debian bookworm-backports main' | sudo tee /etc/apt/sources.list.d/backports.list
```

```bash
sudo apt update
```

```bash
sudo apt install -t bookworm-backports far2l far2l-wx
```

В `bookworm-backports-sloppy` есть и far2l 2.8.0. После обновления far2l достаточно ещё раз
запустить `python3 install.py`: установщик сам переключится на профиль far2l-2.8.

## Особенности

- `far2l --version` в 2.6.5 не существует и **запускает сам far2l** (в сеансе X11 откроется окно).
  Версию смотреть так: `far2l -h | head -1`, или `python3 install.py --detect`.
- В меню приложений четыре ярлыка far2l: два графических и два «(Terminal)». Установщик меняет
  иконку у всех четырёх.
- Окно far2l в X11 имеет класс `far2l` (WM_CLASS) и своей иконки не задаёт, поэтому GNOME берёт
  иконку из `far2l.desktop`. Если в доке осталась старая иконка: Alt+F2 → `r` → Enter
  (перезапуск GNOME Shell, только в X11) или выйти из сеанса и войти снова.
- Тем в far2l 2.6 нет: в «Параметры → Цвета» темы «GNOME Graphite» не будет, это нормально.
  Цвета берутся из `~/.config/far2l/settings/farcolors.ini`.
- Python 3.11 из Debian 12 подходит. Для автоматического первого запуска нужен tmux:
  `sudo apt install tmux`.
- Для снимков в графическом режиме (`tools/snapshot.py`):
  `sudo apt install xvfb xdotool imagemagick python3-pil`.

## Как проверено

Точная версия пакета закреплена в `Containerfile` и записана в `expect.json`; `tools/e2e.py`
сверяет её с тем, что оказалось в контейнере.

`python3 tools/e2e.py debian-12-gnome-x11-far2l-2.6` — контейнер из [Containerfile](Containerfile):
Debian 12 и пакеты `far2l`, `far2l-wx` версии `2.6.5~beta+ds-3~bpo12+1`. В нём: установка
на чистый профиль с автоматическим первым запуском, `--verify`, снимки в графическом режиме
(Xvfb) и в терминальном (tmux), проверка цветов на снимках, повторная установка, откат.
Снимки графического режима — в [screenshots/](screenshots/).

Сам рабочий стол GNOME в контейнере не запускается. То, что относится к GNOME и X11
(класс окна, выбор иконки), проверено по исходникам far2l 2.6.5, wxWidgets 3.2.2,
GTK 3.24.38 и gnome-shell 43.
