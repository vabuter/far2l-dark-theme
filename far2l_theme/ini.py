"""Точечное редактирование ini-файлов far2l без переформатирования остального файла.

Семантика чтения повторяет KeyFileHelper из far2l: одноимённые секции сливаются,
при повторе ключа побеждает последнее значение; комментарий — строка, начинающаяся с ';' или '#'.
"""
import os
import tempfile


class Ini:
    def __init__(self, path):
        self.path = path
        self.lines = []
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="surrogateescape") as fh:
                self.lines = fh.read().split("\n")

    @staticmethod
    def _header(line):
        s = line.strip()
        return s[1:-1] if s.startswith("[") and s.endswith("]") else None

    def _blocks(self, section):
        """Все блоки секции: [(индекс заголовка, индекс конца)]."""
        out, start, name = [], None, None
        for i, line in enumerate(self.lines + ["[]"]):
            h = self._header(line) if i < len(self.lines) else ""
            if h is not None:
                if start is not None and name == section:
                    out.append((start, i))
                start, name = i, h
        return out

    @staticmethod
    def _kv(line):
        s = line.strip()
        if not s or s[0] in ";#" or "=" not in s:
            return None
        k, v = s.split("=", 1)
        return k.strip(), v.strip()

    def sections(self):
        seen = []
        for line in self.lines:
            h = self._header(line)
            if h is not None and h not in seen:
                seen.append(h)
        return seen

    def has_section(self, section):
        return bool(self._blocks(section))

    def items(self, section):
        out = {}
        for start, end in self._blocks(section):
            for line in self.lines[start + 1:end]:
                kv = self._kv(line)
                if kv:
                    out[kv[0]] = kv[1]
        return out

    def get(self, section, key, default=None):
        return self.items(section).get(key, default)

    def set(self, section, values):
        blocks = self._blocks(section)
        if not blocks:
            while self.lines and not self.lines[-1].strip():
                self.lines.pop()
            if self.lines:
                self.lines.append("")
            self.lines.append(f"[{section}]")
            self.lines += [f"{k}={v}" for k, v in values.items()]
            self.lines.append("")
            return
        pending = dict(values)
        for start, end in blocks:
            for i in range(start + 1, end):
                kv = self._kv(self.lines[i])
                if kv and kv[0] in values:
                    self.lines[i] = f"{kv[0]}={values[kv[0]]}"
                    pending.pop(kv[0], None)
        if pending:
            start, end = blocks[-1]
            last = start
            for i in range(start + 1, end):
                if self._kv(self.lines[i]):
                    last = i
            for j, (k, v) in enumerate(pending.items()):
                self.lines.insert(last + 1 + j, f"{k}={v}")

    def text(self):
        return "\n".join(self.lines)

    def save(self):
        write_atomic(self.path, self.text())


def write_atomic(path, text, mode=0o600, follow_symlinks=True):
    """Запись через временный файл и rename: far2l никогда не увидит недописанный файл.
    Права существующего файла сохраняются, новые файлы создаются как у far2l (0600).
    Если path — символьная ссылка, по умолчанию пишется её цель (так делает и far2l,
    чтобы не рвать настройки, хранящиеся в dotfiles); follow_symlinks=False заменяет саму ссылку."""
    if follow_symlinks and os.path.islink(path):
        path = os.path.realpath(path)
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    if os.path.exists(path) and not os.path.islink(path):
        mode = os.stat(path).st_mode & 0o777
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        binary = isinstance(text, bytes)
        with os.fdopen(fd, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8",
                                                                            "errors": "surrogateescape"})) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
