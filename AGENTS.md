# Инструкция для ИИ-агента: установка темы far2l «GNOME Graphite»

Задача: установить тему из этого репозитория в far2l текущего пользователя.

Работа считается сделанной, когда:

1. `python3 install.py --verify` печатает `ИТОГ: всё установлено` и завершается с кодом 0;
2. пользователь получил путь к резервной копии и команду отката.

## Правила

- Не запускать через `sudo`. Всё ставится в домашний каталог, системные файлы (`/usr/...`) не трогать.
- Не завершать процесс far2l самостоятельно: в его редакторе могут быть несохранённые файлы.
  Если far2l запущен, попросите пользователя закрыть его (F10) и дождитесь подтверждения.
- Не править цвета вручную в каталоге настроек. Единственный источник цветов — константы в `install.py`.
- Не удалять резервные копии `*-backup-*.tar.gz`.
- Пакеты (far2l, tmux, Pillow) ставить только с согласия пользователя.

## 1. Проверить окружение

```bash
far2l --version
```

```bash
python3 --version
```

```bash
command -v tmux
```

```bash
pgrep -x far2l
```

- `far2l --version` — нужна 2.6 или новее (проверено на 2.8.0). Если far2l нет, сообщите пользователю
  и предложите установить из пакетов дистрибутива (Fedora: `sudo dnf install far2l`).
- Python 3.8+ обязателен.
- tmux желателен: без него установщик не сможет сам выполнить первый запуск чистого far2l
  (см. «Решение проблем»), а `tools/snapshot.py` не будет работать.
- `pgrep -x far2l` должен ничего не вывести. Иначе — правило про закрытие far2l выше.

Каталог настроек установщик определяет так же, как far2l: `$FARSETTINGS/.config`
(если `FARSETTINGS` — абсолютный путь), иначе `$XDG_CONFIG_HOME/far2l`, иначе `~/.config/far2l`.
Если пользователь запускает far2l с ключом `-u ПУТЬ`, передайте `--config-dir ПУТЬ/.config`.

## 2. Установить

```bash
python3 install.py
```

Строки вывода: `[ok]` — шаг выполнен, `[!]` — предупреждение (прочитайте и передайте пользователю),
`[STOP]` — установка не начата.

Коды выхода: `0` — готово, `2` — far2l запущен (ничего не изменено).

Порядок работы установщика:

1. резервная копия каталога настроек и пользовательских иконок рядом с каталогом настроек
   (`~/.config/far2l-backup-ГГГГММДД-ЧЧММСС.tar.gz`);
2. если в `settings/colors.ini` нет групп раскраски файлов (far2l ни разу не запускался),
   far2l запускается в tmux в терминальном режиме и закрывается, чтобы создать штатные настройки;
3. тема `settings/themes/GNOME Graphite/farcolors.ini` и `[Colors] CurrentTheme` в `settings/colors.ini`;
4. `palette.ini`;
5. цвет под курсором в группах раскраски файлов;
6. Colorer: `plugins/colorer/graphite.hrd`, `user-hrd.xml`, ключи в `plugins/colorer/config.ini`;
7. иконки в `~/.local/share/icons/hicolor/scalable/apps/` и переопределения
   `~/.local/share/applications/far2l.desktop`, `far2ledit.desktop` (только Linux).

Установку можно запускать повторно: результат тот же, каждый запуск делает новую резервную копию.

Полезные ключи: `--skip-icons`, `--skip-colorer`, `--skip-palette`, `--skip-highlight`, `--no-bootstrap`,
`--config-dir DIR`, `--data-home DIR` (вместо `~/.local/share`).
`--force` — только если запущенный far2l точно работает с другим каталогом настроек.

## 3. Проверить

```bash
python3 install.py --verify
```

Все строки должны быть `[ok]` (строка `[-]` означает, что шаг неприменим, это не ошибка).

Визуальная проверка без графического экрана (нужен tmux, для PNG — Pillow). far2l запускается
на копии настроек, настоящие настройки не меняются:

```bash
python3 tools/snapshot.py --out /tmp/far2l-shots
```

Ожидаемая сводка цветов (значения могут отличаться на 1–2 единицы из-за округления):

| Экран | Что должно быть |
|---|---|
| `panels` | фон `#1d1d20` преобладает, есть `#2e2e32` (F-клавиши), `#1c71d8` (заголовок активной панели), `#254165` (курсор) |
| `menu` | есть фон `#36363a` (выпадающее меню) |
| `dialog` | есть фон `#36363a` (диалог создания папки) |
| `warning` | есть фон `#a51d2d` (красное предупреждение) |
| `editor` | фон `#1d1d20`; текст `≈#ffa348` (ключевые слова), `≈#8ff0a4` (строки) — значит, Colorer применил схему `graphite` |

Если вы умеете смотреть изображения, откройте `panels.png` и `editor.png`. Признак проблемы —
синий фон (`#000080` / `#000060`) или бирюзовый курсор (`#008080`).

## 4. Сообщить пользователю

- путь к резервной копии (из строки `[ok] резервная копия: …`);
- откат: `python3 install.py --restore <путь к копии>`;
- тему можно сменить в far2l: F9 → Параметры → Цвета;
- новая иконка в доке или меню может появиться только после выхода из сеанса и повторного входа.

## Решение проблем

| Симптом | Причина и решение |
|---|---|
| `[STOP] far2l запущен` | Попросите пользователя закрыть far2l (F10) и повторите. |
| `[!] не удалось автоматически создать настройки far2l` | Нет tmux или far2l не в `PATH`. Попросите пользователя один раз запустить far2l и выйти по F10, затем повторите `python3 install.py`. |
| `--verify`: `раскраска файлов: 0 групп` | То же: far2l ещё не запускался. |
| `[!] нет явного правила для N ключей` | Новая версия far2l добавила цвета. Они подобраны автоматически по названию; можно добавить точные правила в `FIXED` в `install.py`. |
| `[!] каталог тем far2l не найден` | Старая сборка far2l без тем. Цвета записаны и в `settings/farcolors.ini`; проверьте снимком. |
| far2l всё ещё синий | far2l был открыт во время установки и перезаписал настройки при выходе. Закройте его и установите заново. |
| Редактор синий, остальное тёмное | Colorer не подхватил схему: проверьте `plugins/colorer/config.ini` (`HrdNameTm=graphite`, `TrueMod=1`, `UserHrdPath` указывает на существующий `user-hrd.xml`). |
| `[!] иконки: far2l.desktop не найден` | В дистрибутиве у `.desktop`-файла другое имя. Найдите его (`grep -l '^Exec=far2l' /usr/share/applications/*.desktop`) и добавьте в `DESKTOP_ICONS` в `install.py`. |
| Иконка не сменилась | Выйти из сеанса и войти снова. На macOS иконки не ставятся. |

## Ручная установка (если Python недоступен)

Готовые файлы в `theme/` сгенерированы для far2l 2.8.0. В более новых версиях могут быть новые ключи:
без них соответствующие элементы останутся штатного синего цвета, поэтому по возможности используйте `install.py`.
Ниже `CFG` — каталог настроек far2l (обычно `~/.config/far2l`). far2l должен быть закрыт.

1. Резервная копия: `tar czf ~/.config/far2l-backup-manual.tar.gz -C ~/.config far2l`.
2. Тема: скопировать `theme/farcolors.ini` в `CFG/settings/themes/GNOME Graphite/farcolors.ini`.
3. В `CFG/settings/colors.ini` в секции `[Colors]` (создать, если нет): `CurrentTheme=GNOME Graphite`
   и `CurrentThemeIsSystemWide=0`.
4. Скопировать `theme/palette.ini` в `CFG/palette.ini`.
5. В каждой секции `[Colors/Highlight/GroupN]` файла `CFG/settings/colors.ini`, где `CursorColor`
   и `NormalColor` не равны `0x0`: `CursorColor` = значение `NormalColor`, `CursorColorMask` = значение `NormalColorMask`.
6. Colorer: скопировать `theme/graphite.hrd` в `CFG/plugins/colorer/graphite.hrd`; создать `CFG/plugins/colorer/user-hrd.xml`:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <hrd-sets>
     <hrd class="rgb" name="graphite" description="GNOME Graphite">
       <location link="АБСОЛЮТНЫЙ_ПУТЬ_К/graphite.hrd"/>
     </hrd>
   </hrd-sets>
   ```

   В `CFG/plugins/colorer/config.ini`, секция `[Settings]`: `HrdNameTm=graphite`, `HrdName=black`,
   `TrueMod=1`, `UserHrdPath=` абсолютный путь к `user-hrd.xml`.
7. Иконки (Linux): `icons/*.svg` скопировать в `~/.local/share/icons/hicolor/scalable/apps/`;
   `/usr/share/applications/far2l.desktop` и `far2ledit.desktop` скопировать в `~/.local/share/applications/`
   и заменить в них `Icon=` на `far2l-graphite` и `far2ledit-graphite` соответственно.

## Как это устроено (для доработок)

- Темы far2l: `CFG/settings/themes/<имя>/farcolors.ini`, выбранная тема — `[Colors] CurrentTheme`
  в `settings/colors.ini`. Без темы far2l читает `settings/farcolors.ini`.
- Значение цвета в `farcolors.ini` far2l читает до `;`:
  `background:#rrggbb foreground:#rrggbb, B_<ИНДЕКС> | F_<ИНДЕКС>`. RGB используется в TrueColor,
  индексы — запасной вариант для 16-цветных терминалов. После `;` — комментарий (`back_rgb(...)`).
- Ключ, которого нет в файле темы, far2l рисует штатным синим. Поэтому установщик собирает список ключей
  из готового файла, штатных тем far2l (`<prefix>/share/far2l/themes`) и текущих настроек пользователя.
- Группы раскраски файлов (`[Colors/Highlight/GroupN]`) задают только цвет текста: маска
  `0xfffffffd0f` покрывает индекс и RGB цвета текста. Индексные цвета рисуются через `palette.ini`.
- Colorer при `TrueMod=1` берёт RGB-схему `HrdNameTm`. Пользовательские схемы подключаются через
  `UserHrdPath` (файл `<hrd-sets>`).
- Иконки: GNOME сопоставляет окно far2l с `far2l.desktop` по app_id, поэтому достаточно переопределить
  `.desktop` в `~/.local/share/applications` с новым `Icon=`.
- После изменения цветов в `install.py`: `python3 install.py --export theme`, затем пересоздать снимки
  (`python3 tools/snapshot.py --out …`) и скопировать нужные PNG в `docs/screen-*.png`.

## Структура репозитория

```
install.py            установщик: цвета, установка, --verify, --restore, --export
theme/farcolors.ini   готовый файл темы (сгенерирован install.py --export theme)
theme/palette.ini     готовая палитра
theme/graphite.hrd    схема подсветки синтаксиса Colorer
icons/                иконки far2l и редактора far2l (SVG)
tools/snapshot.py     снимки экранов far2l в tmux (PNG + сводка цветов)
docs/                 картинки для README
```
