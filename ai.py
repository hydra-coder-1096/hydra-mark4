"""AI Base — перевод текста на естественном языке в команды Hydra DSL.

Провайдер: переменная HYDRA_AI_PROVIDER = auto (по умолчанию) | gemini | openai | rules
  auto   — gemini, если есть GEMINI_API_KEY; иначе openai, если есть OPENAI_API_KEY; иначе rules
  gemini — REST API Gemini без сторонних пакетов, ключ только из GEMINI_API_KEY
  openai — пакет openai, ключ только из OPENAI_API_KEY
  rules  — локальные правила без AI; включаются сами, если ключа нет или AI не ответил
Модель: HYDRA_MODEL (иначе значение из DEFAULT_MODELS для выбранного провайдера).
Base H про провайдера ничего не знает: на выходе всегда команды DSL.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from hydra_dsl import build_command, parse_lines

DEFAULT_MODELS = {"gemini": "gemini-3.5-flash-lite", "openai": "gpt-5.6-terra"}
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_COMMANDS = 5
MAX_INPUT_CHARS = 6000

SYSTEM_PROMPT = """You convert a bug report into Hydra DSL commands for a local code analyzer.
Reply with commands only: one per line, at most 5, no prose, no markdown.

Syntax: OPERATION TARGET key=value ...   (wrap values containing spaces in double quotes)
ANALYZE <python|javascript|unknown> error=<ErrorType> message="<error message>" file="<path>" line=<n>
SEARCH <project|logs> query="<text to find in repository files>"
INSPECT file path="<path>" line=<n>

Rules:
- If the report contains an error, start with exactly one ANALYZE. Take error type and message from the final error line; file and line from the last traceback frame that belongs to the user's project (not site-packages, node_modules or the standard library). Omit file/line if unknown.
- Add SEARCH for an undefined name, missing attribute, failed import name or missing key (query = that name). Do not SEARCH for missing modules or file paths.
- Use INSPECT only for files explicitly named in the report. Never invent paths.
- If there is no error, use SEARCH/INSPECT for names and files mentioned in the report.

Example:
ANALYZE python error=NameError message="name 'greet' is not defined" file="main.py" line=3
SEARCH project query="greet"
"""

ERR_RE = re.compile(r"\b(?:[A-Za-z_]\w*\.)*([A-Z]\w*(?:Error|Exception))\b(?:[ \t]*:[ \t]*([^\n]*))?")
PY_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+)')
JS_FRAME_RE = re.compile(r"([\w./\\-]+\.(?:js|mjs|cjs|ts|jsx|tsx)):(\d+)(?::\d+)?")
EXTERNAL_RE = re.compile(r"site-packages|dist-packages|node_modules|node:internal|^<|[/\\]lib[/\\]python3")
FILE_RE = re.compile(r"(?<![\w/.-])([\w./-]+\.(?:py|js|ts|jsx|tsx|html|css|json|ya?ml|toml))\b")
CODE_RE = re.compile(r"`([^`\n]{2,60})`")
JS_ONLY = {"ReferenceError", "RangeError", "EvalError", "URIError"}
TERM_PATTERNS = (  # модули и пути Base H проверяет сам, поиск нужен для имён
    r"cannot import name '(\w+)'",
    r"name '(\w+)' is not defined",
    r"has no attribute '(\w+)'",
    r"^(\w+) is not defined",
    r"\(reading '(\w+)'\)",
)


class _NoKey(Exception):
    pass


def translate(text, provider=None):
    """Текст -> (команды DSL в виде dict, info{provider, dsl, warnings})."""
    text = text or ""
    if not text.strip():
        return [], {"provider": "rules", "dsl": [], "warnings": ["пустой текст"]}
    provider, warnings = _pick_provider(provider), []
    if provider in CALLERS:
        try:
            commands = CALLERS[provider](text)
            if commands:
                return commands, _info(f"{provider}/{_model(provider)}", commands, warnings)
            warnings.append("AI не вернул ни одной корректной команды — использую правила")
        except _NoKey as exc:
            warnings.append(f"{exc} не найден — работаю без AI (правила)")
        except ImportError:
            warnings.append(f"пакет для {provider} не установлен — использую правила")
        except Exception as exc:  # сеть, лимиты, неверная модель — Base H всё равно должен отработать
            warnings.append(f"AI недоступен ({type(exc).__name__}: {str(exc)[:300]}) — использую правила")
    elif provider == "none":
        warnings.append("GEMINI_API_KEY / OPENAI_API_KEY не найдены — работаю без AI (правила)")
    elif provider != "rules":
        warnings.append(f"неизвестный провайдер '{provider}' — использую правила")
    commands, _ = parse_lines("\n".join(rules_translate(text)))
    return commands[:MAX_COMMANDS], _info("rules", commands[:MAX_COMMANDS], warnings)


def _key(name):
    return os.environ.get(name, "").strip()


def _pick_provider(provider):
    provider = (provider or os.environ.get("HYDRA_AI_PROVIDER") or "auto").strip().lower()
    if provider != "auto":
        return provider
    if _key("GEMINI_API_KEY"):
        return "gemini"
    if _key("OPENAI_API_KEY"):
        return "openai"
    return "none"


def _info(provider, commands, warnings):
    dsl = [build_command(c["operation"], c["target"], c["params"]) for c in commands]
    return {"provider": provider, "dsl": dsl, "warnings": warnings}


def _model(provider):
    return _key("HYDRA_MODEL") or DEFAULT_MODELS.get(provider, "")


def _clip(text):
    if len(text) <= MAX_INPUT_CHARS:
        return text
    head = MAX_INPUT_CHARS // 3
    return text[:head] + "\n...\n" + text[-(MAX_INPUT_CHARS - head):]


def _from_gemini(text):
    key = _key("GEMINI_API_KEY")
    if not key:
        raise _NoKey("GEMINI_API_KEY")
    model = _model("gemini").removeprefix("models/")
    body = {"system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": _clip(text)}]}]}
    request = urllib.request.Request(
        GEMINI_URL.format(model=urllib.parse.quote(model, safe="")), method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Gemini HTTP {exc.code}: {detail}") from None
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    answer = "\n".join(p.get("text", "") for p in parts if not p.get("thought"))
    commands, _ = parse_lines(answer)
    return commands[:MAX_COMMANDS]


def _from_openai(text):
    key = _key("OPENAI_API_KEY")
    if not key:
        raise _NoKey("OPENAI_API_KEY")
    from openai import OpenAI

    client = OpenAI(api_key=key, timeout=60, max_retries=1)
    response = client.responses.create(model=_model("openai"), instructions=SYSTEM_PROMPT, input=_clip(text))
    commands, _ = parse_lines(getattr(response, "output_text", "") or "")
    return commands[:MAX_COMMANDS]


CALLERS = {"gemini": _from_gemini, "openai": _from_openai}


# ---------- правила без AI ----------

def rules_translate(text):
    """Текст -> список строк DSL по регулярным выражениям."""
    text = text or ""
    commands = []
    matches = list(ERR_RE.finditer(text))
    if matches:
        last = matches[-1]
        error = last.group(1)
        message = (last.group(2) or "").strip().strip("`").strip()[:200]
        lang = _language(text, error)
        path, line = _location(text, lang)
        commands.append(build_command("ANALYZE", lang, {"error": error, "message": message, "file": path, "line": line}))
        term = _search_term(error, message)
        if term:
            commands.append(build_command("SEARCH", "project", {"query": term}))
    else:
        for path in dict.fromkeys(FILE_RE.findall(text)):
            commands.append(build_command("INSPECT", "file", {"path": path}))
        for term in dict.fromkeys(CODE_RE.findall(text)):
            commands.append(build_command("SEARCH", "project", {"query": term}))
        if not commands:
            commands.append(build_command("ANALYZE", "unknown", {"message": " ".join(text.split())[:200]}))
    return commands[:MAX_COMMANDS]


def _language(text, error):
    if "Traceback (most recent call last)" in text or PY_FRAME_RE.search(text):
        return "python"
    if error in JS_ONLY or JS_FRAME_RE.search(text) or "Uncaught" in text or "Cannot read propert" in text:
        return "javascript"
    return "python" if error else "unknown"


def _location(text, lang):
    frames = JS_FRAME_RE.findall(text) if lang == "javascript" else PY_FRAME_RE.findall(text)[::-1]
    own = [f for f in frames if not EXTERNAL_RE.search(f[0])]
    return (own or frames or [(None, None)])[0]


def _search_term(error, message):
    for pattern in TERM_PATTERNS:
        m = re.search(pattern, message)
        if m:
            return m.group(1)
    if error == "KeyError":
        key = message.strip().strip("'\"")
        if re.fullmatch(r"[\w.-]{1,60}", key):
            return key
    return None
