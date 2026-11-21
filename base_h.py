"""Base H — локальное выполнение команд Hydra DSL. Работает без AI и без сети.

  execute(command) -> результат одной команды (команда из hydra_dsl.parse_command)
  run(commands)    -> итог: what_happened / where / why / how_to_fix / confidence
"""
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache", "dist", "build"}
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".html", ".css", ".json",
            ".toml", ".cfg", ".ini", ".yml", ".yaml", ".txt", ".sh"}
SOURCE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"}
LOG_EXT = {".log", ".out", ".txt"}
PRIVATE_EXT = {".pem", ".key", ".p12", ".pfx"}
MAX_FILE_BYTES = 1_000_000
MAX_HITS = 20

PIP_NAMES = {"cv2": "opencv-python", "PIL": "pillow", "yaml": "pyyaml", "sklearn": "scikit-learn",
             "bs4": "beautifulsoup4", "dotenv": "python-dotenv", "dateutil": "python-dateutil", "jwt": "pyjwt"}
KNOWN_MODULES = set(sys.stdlib_module_names) | {"requests", "numpy", "pandas", "openai", "flask", "django"}
PY_LITERALS = {"null": "None", "true": "True", "false": "False"}
TERMINAL_LINE = re.compile(r"^\s*(?:EOF\b|cat\s+>|python3?\s+-c\b|pip3?\s+install\b|git\s+\w|\$\s)")

PY_ERRORS = {
    "ModuleNotFoundError": ("Python не нашёл модуль: пакет не установлен в текущем окружении или имя написано с ошибкой.",
                            ["Установи пакет: `pip install <имя>`", "Добавь пакет в requirements.txt",
                             "Если это модуль проекта — запускай из корня репозитория"]),
    "ImportError": ("Модуль найден, но нужного имени в нём нет, либо импорт циклический.",
                    ["Проверь, что имя действительно есть в модуле", "Проверь версию пакета: `pip show <пакет>`",
                     "При циклическом импорте перенеси import внутрь функции"]),
    "NameError": ("Используется имя, которое не определено в этой области видимости.",
                  ["Проверь опечатку в имени", "Определи переменную/функцию до использования", "Добавь недостающий import"]),
    "UnboundLocalError": ("Локальная переменная используется до присваивания (часто присваивание только внутри if/цикла).",
                          ["Присвой переменной значение до if/цикла", "Нужна внешняя переменная — передай её аргументом"]),
    "TypeError": ("Функция или операция получила значение не того типа или не то число аргументов.",
                  ["Выведи тип: `print(type(x))`", "Сверь аргументы с сигнатурой функции",
                   "Приведи тип явно: `int()`, `str()`, `list()`"]),
    "ValueError": ("Тип значения правильный, но само значение недопустимо.",
                   ["Проверь входные данные перед преобразованием", "Оберни преобразование в `try/except ValueError`"]),
    "IndexError": ("Обращение к индексу за пределами списка или строки.",
                   ["Проверь длину: `len(x)`", "Убедись, что список не пустой перед `x[0]`"]),
    "KeyError": ("В словаре нет такого ключа.",
                 ["Используй `d.get(key)` со значением по умолчанию", "Проверь наличие: `if key in d`",
                  "Выведи ключи: `print(d.keys())`"]),
    "AttributeError": ("У объекта нет такого атрибута или метода; часто объект оказался `None`.",
                       ["Проверь тип объекта: `print(type(obj))`", "Проверь опечатку в имени атрибута",
                        "Убедись, что функция, вернувшая объект, не вернула `None`"]),
    "SyntaxError": ("Код нарушает синтаксис Python — файл не запускается вообще.",
                    ["Открой указанную строку и строку перед ней", "Проверь скобки, кавычки и двоеточия",
                     "Удали из файла посторонние строки (например, команды терминала)"]),
    "IndentationError": ("Неправильные отступы.",
                         ["Используй 4 пробела на уровень, без табов", "Проверь отступ строки и блока над ней"]),
    "TabError": ("В отступах смешаны табы и пробелы.", ["Замени табы на 4 пробела во всём файле"]),
    "FileNotFoundError": ("Файл или папка по пути не существует (или путь считается от другой папки).",
                          ["Проверь путь и текущую папку: `pwd`", "Строй путь от файла: `Path(__file__).parent / 'имя'`"]),
    "PermissionError": ("Нет прав на чтение/запись файла или папки.",
                        ["Проверь права: `ls -l`", "Пиши в папку проекта, а не в системные папки"]),
    "ZeroDivisionError": ("Деление на ноль.", ["Проверь делитель перед делением: `if b != 0`"]),
    "RecursionError": ("Функция вызывает сама себя без условия выхода.",
                       ["Добавь или исправь условие выхода из рекурсии", "Замени рекурсию циклом"]),
    "JSONDecodeError": ("Строка не является корректным JSON (часто пустой ответ или HTML вместо JSON).",
                        ["Выведи сырой текст перед `json.loads`", "Проверь код ответа сервера и что ответ не пустой"]),
    "UnicodeDecodeError": ("Файл прочитан не в той кодировке.",
                           ["Открой файл с `encoding='utf-8'`", "Для неизвестной кодировки добавь `errors='replace'`"]),
}
JS_ERRORS = {
    "ReferenceError": ("Используется переменная, которая не объявлена.",
                       ["Проверь опечатку", "Объяви переменную через `let`/`const` до использования",
                        "Проверь import или подключение скрипта"]),
    "TypeError": ("Значение не того типа; чаще всего обращение к свойству `undefined` или `null`.",
                  ["Проверь значение перед обращением: `obj?.prop`", "Выведи значение: `console.log(obj)`",
                   "Убедись, что данные уже загружены (async/await)"]),
    "SyntaxError": ("Код нарушает синтаксис JavaScript (или JSON.parse получил не JSON).",
                    ["Открой указанную строку", "Проверь скобки, запятые и кавычки"]),
    "RangeError": ("Значение вне допустимого диапазона (часто бесконечная рекурсия).",
                   ["Проверь условие выхода из рекурсии", "Проверь размеры массивов и числа"]),
}


# ---------- файлы ----------

def _root(root):
    return Path(root or os.getcwd()).resolve()


def _is_private(rel):
    return rel.name.startswith(".env") or rel.suffix.lower() in PRIVATE_EXT or any(p in SKIP_DIRS for p in rel.parts)


def _locate(root, path):
    """Путь из команды/traceback -> файл внутри проекта или None. За пределы root не выходит."""
    if not path:
        return None
    parts = Path(str(path).strip().replace("\\", "/")).parts
    for i in range(len(parts)):
        cand = root.joinpath(*parts[i:]).resolve()
        if cand.is_relative_to(root) and cand.is_file() and not _is_private(cand.relative_to(root)):
            return cand
    return None


def _iter_files(root, exts=None):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not (d.startswith(".") and d != ".github"))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root)
            if (exts is None or path.suffix.lower() in exts) and not _is_private(rel) \
                    and path.resolve().is_relative_to(root):
                yield path, rel


def _read_lines(path, strict=True):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        if strict:
            return path.read_text(encoding="utf-8").splitlines()
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except (UnicodeDecodeError, OSError):
        return None


def _snippet(lines, line=None, context=3, head=40):
    if line and 1 <= line <= len(lines):
        start, end = max(1, line - context), min(len(lines), line + context)
    else:
        start, end = 1, min(len(lines), head)
    width = len(str(end))
    return "\n".join(f"{'>' if n == line else ' '} {n:>{width}} | {lines[n - 1]}" for n in range(start, end + 1))


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _norm(name):
    return name.strip().lower().replace("_", "-")


def _requirements(root):
    path = root / "requirements.txt"
    if not path.is_file():
        return set()
    names = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            names.add(_norm(re.split(r"[<>=!~\[;@ ]", line, maxsplit=1)[0]))
    return names


def _definitions(root, name, limit=5):
    n = re.escape(name)
    pattern = re.compile(rf"^\s*(?:async\s+def|def|class|function|let|const|var)\s+{n}\b|^\s*{n}\s*(?::[^=]*)?=(?!=)")
    found = []
    for path, rel in _iter_files(root, SOURCE_EXT):
        for i, text in enumerate(_read_lines(path) or [], 1):
            if pattern.search(text):
                found.append({"file": rel.as_posix(), "line": i, "text": text.strip()[:200]})
                if len(found) >= limit:
                    return found
    return found


def _error(message):
    return {"status": "error", "message": message}


# ---------- операции ----------

def _search(root, target, params):
    query = (params.get("query") or params.get("type") or "").strip()
    if not query:
        return _error('SEARCH: нужен параметр query="..."')
    exts = LOG_EXT if (target or "").lower() == "logs" else CODE_EXT
    # имя переменной/функции ищем целым словом, остальное — подстрокой
    if re.fullmatch(r"\w+", query):
        word = re.compile(rf"\b{re.escape(query)}\b", re.IGNORECASE)
        match = word.search
    else:
        needle = query.lower()
        match = lambda text: needle in text.lower()  # noqa: E731
    hits, total = [], 0
    for path, rel in _iter_files(root, exts):
        for i, text in enumerate(_read_lines(path) or [], 1):
            if match(text):
                total += 1
                if len(hits) < MAX_HITS:
                    hits.append({"file": rel.as_posix(), "line": i, "text": text.strip()[:200]})
    return {"status": "ok", "query": query, "hits": hits, "total": total}


def _inspect(root, target, params):
    path = params.get("path") or (target if target and target.lower() != "file" else None)
    if not path:
        return _error('INSPECT: нужен параметр path="..."')
    found = _locate(root, path)
    if not found:
        return _error(f"INSPECT: файл не найден в проекте или закрыт для чтения: {path}")
    lines = _read_lines(found, strict=False)
    if lines is None:
        return _error(f"INSPECT: файл слишком большой или не читается: {path}")
    line = _int(params.get("line"))
    context = _int(params.get("context"))
    context = 5 if context is None else max(0, min(context, 50))
    note = f"строка {line} вне файла (строк: {len(lines)})" if line and not 1 <= line <= len(lines) else None
    return {"status": "ok", "file": found.relative_to(root).as_posix(), "line": line,
            "lines": len(lines), "snippet": _snippet(lines, line, context), "note": note}


def _analyze(root, target, params):
    lang = (target or "unknown").lower()
    lang = "javascript" if lang in ("js", "javascript", "node", "typescript", "ts") else lang
    error = (params.get("error") or "").strip().rsplit(".", 1)[-1] or None
    message = (params.get("message") or "").strip()

    if lang == "javascript":
        entry = JS_ERRORS.get(error)
    elif lang == "python":
        entry = PY_ERRORS.get(error)
    else:
        entry = PY_ERRORS.get(error) or JS_ERRORS.get(error)

    if entry:
        why, fixes = entry[0], list(entry[1])
    else:
        why = "Тип ошибки не распознан — нужен полный текст ошибки (traceback)."
        fixes = ["Приложи полный traceback целиком", "Укажи команду запуска и что ожидалось"]

    where, lines, notes = None, None, []
    line = _int(params.get("line"))
    if params.get("file"):
        found = _locate(root, params["file"])
        lines = _read_lines(found, strict=False) if found else None
        if lines is not None:
            where = {"file": found.relative_to(root).as_posix(), "line": line, "snippet": _snippet(lines, line)}
        else:
            notes.append(f"Файл `{params['file']}` не найден в репозитории — ошибка может быть во внешней библиотеке")

    special_why, specific = _specific(root, lang, error, message, where, lines, line)
    return {"status": "ok", "language": lang, "error": error, "message": message, "known": entry is not None,
            "why": special_why or why, "how_to_fix": (specific or fixes) + notes, "where": where}


def _specific(root, lang, error, message, where, lines, line):
    """Конкретные находки по проекту -> (уточнённое «почему» или None, список шагов)."""
    why, fixes = None, []

    hint = re.search(r"Did you mean:? '?([\w.]+)'?\?", message)
    if hint:
        fixes.append(f"Python подсказывает правильное имя: `{hint.group(1)}`")

    if error == "ModuleNotFoundError":
        m = re.search(r"No module named '([\w.]+)'", message)
        if m:
            mod = m.group(1).split(".")[0]
            pkg = PIP_NAMES.get(mod, mod)
            if (root / f"{mod}.py").is_file() or (root / mod).is_dir():
                fixes.append(f"`{mod}` — модуль этого проекта: запускай команду из корня репозитория")
            elif _norm(pkg) in _requirements(root):
                fixes.append(f"`{pkg}` есть в requirements.txt, но не установлен: `pip install -r requirements.txt`")
            else:
                fixes += [f"Установи: `pip install {pkg}`", f"Добавь строку `{pkg}` в requirements.txt"]

    elif error in ("NameError", "ReferenceError"):
        m = re.search(r"name '(\w+)' is not defined", message) or re.search(r"^(\w+) is not defined", message)
        if m:
            name = m.group(1)
            if lang != "javascript" and name in PY_LITERALS:
                fixes.append(f"В Python пиши `{PY_LITERALS[name]}`, а не `{name}`")
            else:
                defs = _definitions(root, name)
                if not defs:
                    fixes.append(f"`{name}` нигде в проекте не определено — проверь опечатку")
                elif where and defs[0]["file"] == where["file"]:
                    fixes.append(f"`{name}` определено в этом же файле на строке {defs[0]['line']} — "
                                 f"определение должно идти до использования и быть в той же области видимости")
                elif defs[0]["file"].endswith(".py"):
                    module = defs[0]["file"][:-3].replace("/", ".")
                    fixes.append(f"`{name}` определено в `{defs[0]['file']}:{defs[0]['line']}` — "
                                 f"добавь `from {module} import {name}`")
                else:
                    fixes.append(f"`{name}` найдено в `{defs[0]['file']}:{defs[0]['line']}` — подключи этот файл")

    elif error == "AttributeError":
        if "'NoneType' object" in message:
            why = "Объект оказался `None`: функция ничего не вернула (нет `return`) или поиск не дал результата."
            fixes.append("Найди, откуда пришло значение, и проверь `if obj is None` перед обращением")
        m = re.search(r"module '([\w.]+)' has no attribute '(\w+)'", message)
        if m:
            mod, attr = m.group(1).split(".")[0], m.group(2)
            if mod in KNOWN_MODULES and (root / f"{mod}.py").is_file():
                why = f"Файл проекта `{mod}.py` перекрывает настоящий модуль `{mod}`."
                fixes.append(f"Переименуй `{mod}.py` (и удали `__pycache__`), затем запусти снова")
            elif (root / f"{mod}.py").is_file():
                fixes.append(f"Проверь, что в `{mod}.py` есть `{attr}` и имя написано так же")
            else:
                fixes.append(f"Проверь версию: `pip show {mod}` — в ней может не быть `{attr}`")

    elif error == "TypeError" and lang != "javascript":
        if m := re.search(r"missing \d+ required positional arguments?: (.+)", message):
            fixes.append(f"Передай при вызове недостающие аргументы: {m.group(1)}")
        elif re.search(r"takes \d+ positional arguments? but \d+ (?:was|were) given", message):
            fixes.append("Число аргументов не совпадает: для метода класса проверь, что первым параметром стоит `self`")
        elif m := re.search(r"unsupported operand type\(s\) for .+: '(\w+)' and '(\w+)'", message):
            fixes.append(f"Нельзя смешивать `{m.group(1)}` и `{m.group(2)}` — приведи к одному типу")
        elif "'NoneType' object" in message:
            why = "Значение оказалось `None` там, где ждали объект."
            fixes.append("Проверь, что функция возвращает значение (`return`)")

    elif error == "TypeError" and lang == "javascript":
        if m := re.search(r"\(reading '(\w+)'\)", message):
            fixes.append(f"При чтении `{m.group(1)}` объект был undefined/null — используй `obj?.{m.group(1)}` "
                         f"и проверь, что данные загружены")

    elif error == "KeyError":
        key = message.strip().strip("'\"")
        if key:
            fixes.append(f"Ключа `{key}` нет — используй `.get('{key}')` или проверь, откуда пришли данные")

    elif error == "FileNotFoundError":
        m = re.search(r"No such file or directory: '([^']+)'", message)
        if m:
            missing = m.group(1)
            found = _locate(root, missing) or next(
                (p for p, _ in _iter_files(root) if p.name == Path(missing).name), None)
            if found:
                fixes.append(f"Файл есть в проекте: `{found.relative_to(root).as_posix()}` — путь считается от текущей "
                             f"папки: запускай из корня или строй путь через `Path(__file__).parent`")
            else:
                fixes.append(f"Файла `{missing}` нет в репозитории — создай его или исправь путь")

    if error in ("SyntaxError", "IndentationError", "TabError") and lines:
        lo, hi = (max(1, line - 3), min(len(lines), line + 3)) if line else (1, len(lines))
        for n in range(lo, hi + 1):
            if TERMINAL_LINE.search(lines[n - 1]):
                fixes.insert(0, f"Строка {n} похожа на команду терминала (`{lines[n - 1].strip()[:60]}`) — "
                                f"она попала в файл случайно, удали её")
                break

    return why, fixes


HANDLERS = {"ANALYZE": _analyze, "SEARCH": _search, "INSPECT": _inspect}


def execute(command, root=None):
    """Выполнить одну команду DSL локально."""
    if not command:
        return _error("Пустая команда")
    operation = (command.get("operation") or "").upper()
    target = command.get("target")
    params = command.get("params") or {}
    handler = HANDLERS.get(operation)
    if handler is None:
        return {"status": "error", "operation": operation, "target": target, "params": params,
                "message": f"Неизвестная операция: {operation}"}
    try:
        result = handler(_root(root), target, params)
    except OSError as exc:
        result = _error(f"{operation}: ошибка доступа к файлам: {exc}")
    return {"status": result.pop("status"), "operation": operation, "target": target, "params": params, **result}


def run(commands, root=None):
    """Выполнить список команд и собрать итоговый разбор."""
    results = [execute(c, root) for c in commands]
    ok = [r for r in results if r["status"] == "ok"]
    analyses = [r for r in ok if r["operation"] == "ANALYZE"]
    main = next((r for r in analyses if r["known"]), analyses[0] if analyses else None)

    where, seen = [], set()

    def add(loc):
        key = (loc["file"], loc.get("line"))
        if key not in seen:
            seen.add(key)
            where.append(loc)

    if main and main["where"]:
        add(main["where"])
    for r in ok:
        if r["operation"] == "INSPECT":
            add({"file": r["file"], "line": r["line"], "snippet": r["snippet"]})
        elif r["operation"] == "SEARCH":
            for hit in r["hits"][:5]:
                add(dict(hit))

    if main is None:
        what = "Тип ошибки не указан — показываю найденное в проекте" if where else "Ошибка в тексте не найдена"
        why = None
        fixes = ["Для точного разбора приложи полный текст ошибки (traceback)",
                 "Укажи команду, которой запускал, и что ожидалось"]
        confidence = "low"
    else:
        what = ": ".join(x for x in (main["error"], main["message"]) if x) or "Ошибка без названия"
        why, fixes = main["why"], main["how_to_fix"]
        confidence = ("high" if main["where"] else "medium") if main["known"] else "low"

    return {"what_happened": what, "where": where, "why": why, "how_to_fix": fixes, "confidence": confidence,
            "errors": [r["message"] for r in results if r["status"] == "error"], "results": results}
