"""Hydra DSL — разбор и сборка команд.

Синтаксис:  <OPERATION> <TARGET> [key=value ...]
Значения с пробелами — в двойных кавычках:  query="где analyze_text"

Операции (выполняет Base H):
  ANALYZE <python|javascript|unknown> error=<Тип> [message="..."] [file="путь"] [line=N]
  SEARCH  <project|logs> query="текст"
  INSPECT file path="путь" [line=N] [context=N]
"""
import re
import shlex

OPERATIONS = ("ANALYZE", "SEARCH", "INSPECT")
_BARE = re.compile(r"[\w./:-]+")
_LIST_PREFIX = re.compile(r"^(?:[-*]\s+|\d+[.)]\s+)")


class DSLError(ValueError):
    """Строка не является корректной командой Hydra DSL."""


def parse_command(command):
    """'ANALYZE python error=X' -> {'operation': 'ANALYZE', 'target': 'python', 'params': {'error': 'X'}}"""
    if not command or not command.strip():
        return None
    try:
        parts = shlex.split(command.strip())
    except ValueError as exc:  # незакрытая кавычка
        raise DSLError(f"не удалось разобрать '{command.strip()}': {exc}") from None
    if not parts:
        return None
    operation, target, params = parts[0].upper(), None, {}
    for token in parts[1:]:
        if "=" in token:
            key, value = token.split("=", 1)
            params[key.strip().lower()] = value
        elif target is None:
            target = token
        else:
            raise DSLError(f"лишний аргумент без '=': {token}")
    return {"operation": operation, "target": target, "params": params}


def quote(value):
    """Значение -> токен DSL (в кавычках, если нужно)."""
    text = " ".join(str(value).split())
    if _BARE.fullmatch(text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_command(operation, target=None, params=None):
    """('ANALYZE', 'python', {'error': 'X'}) -> 'ANALYZE python error=X'. Пустые значения пропускаются."""
    parts = [operation.upper()]
    if target:
        parts.append(quote(target))
    for key, value in (params or {}).items():
        if value is not None and str(value).strip():
            parts.append(f"{key}={quote(value)}")
    return " ".join(parts)


def parse_lines(text):
    """Многострочный текст (например, ответ AI) -> (команды, отклонённые строки)."""
    commands, rejected = [], []
    for raw in (text or "").splitlines():
        line = _LIST_PREFIX.sub("", raw.strip().strip("`").strip())
        if not line or line.startswith("#"):
            continue
        if line.split(None, 1)[0].upper() not in OPERATIONS:
            rejected.append(raw)
            continue
        try:
            commands.append(parse_command(line))
        except DSLError:
            rejected.append(raw)
    return commands, rejected
