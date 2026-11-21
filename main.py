"""Hydra-mark4 — точка входа.

  python main.py ask "текст ошибки"            AI Base -> DSL -> Base H
  python main.py ask -f error.log              то же, текст из файла
  python main.py run "ANALYZE python error=X"  DSL сразу в Base H (без AI)
  python main.py issue 12 [--post]             разбор GitHub issue (+ комментарий)

Флаги для всех команд: --json  --no-ai  --show-dsl
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import ai
import base_h
import github_client
from hydra_dsl import DSLError, parse_command

CONFIDENCE = {"high": "высокая", "medium": "средняя", "low": "низкая"}


def load_dotenv(path=".env"):
    """KEY=value из .env -> переменные окружения. Уже заданные (секреты Codespaces/Actions) не трогает."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and not os.environ.get(key):
            os.environ[key] = value


def analyze_text(text, use_ai=True):
    """Текст -> AI Base -> команды DSL -> Base H -> (отчёт, список DSL)."""
    commands, info = ai.translate(text, provider=None if use_ai else "rules")
    for warning in info["warnings"]:
        print(f"! {warning}", file=sys.stderr)
    report = base_h.run(commands)
    report["provider"] = info["provider"]
    return report, info["dsl"]


def to_markdown(report, title="Hydra: разбор проблемы"):
    out = [f"## {title}", "", f"**Что случилось:** {report['what_happened']}", ""]
    if report["where"]:
        out.append("**Где:**")
        for loc in report["where"]:
            place = f"`{loc['file']}:{loc['line']}`" if loc.get("line") else f"`{loc['file']}`"
            out.append(f"- {place} — `{loc['text'].replace('`', chr(39))}`" if loc.get("text") else f"- {place}")
            if loc.get("snippet"):
                out += ["", "````", loc["snippet"], "````", ""]
        out.append("")
    if report.get("why"):
        out += [f"**Почему:** {report['why']}", ""]
    out.append("**Как исправить:**")
    out += [f"{i}. {step}" for i, step in enumerate(report["how_to_fix"], 1)]
    out += ["", f"**Уверенность:** {CONFIDENCE.get(report['confidence'], report['confidence'])}"]
    if report.get("errors"):
        out += ["", "**Не выполнено:** " + "; ".join(report["errors"])]
    if report.get("provider"):
        out += ["", f"<sub>hydra-mark4 · Base H · команды: {report['provider']}</sub>"]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def _read_text(args):
    if args.file:
        return Path(args.file).read_text(encoding="utf-8", errors="replace")
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ValueError('нужен текст: python main.py ask "..." или -f файл')


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="вывести сырой JSON")
    common.add_argument("--no-ai", action="store_true", help="не вызывать AI, только правила")
    common.add_argument("--show-dsl", action="store_true", help="показать команды DSL")

    parser = argparse.ArgumentParser(prog="main.py", description="Hydra-mark4: AI Base -> Hydra DSL -> Base H")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ask", parents=[common], help="разобрать текст ошибки")
    p.add_argument("text", nargs="?", help="текст ошибки (или -f файл, или stdin)")
    p.add_argument("-f", "--file", help="взять текст из файла")

    p = sub.add_parser("run", parents=[common], help="выполнить команды DSL напрямую (без AI)")
    p.add_argument("commands", nargs="+", help='например: "ANALYZE python error=NameError"')

    p = sub.add_parser("issue", parents=[common], help="разобрать GitHub issue")
    p.add_argument("number", type=int, help="номер issue")
    p.add_argument("--repo", help="owner/name (по умолчанию $GITHUB_REPOSITORY)")
    p.add_argument("--post", action="store_true", help="опубликовать результат комментарием")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    load_dotenv()
    repo = None
    try:
        if args.cmd == "run":
            commands = [c for c in (parse_command(line) for line in args.commands) if c]
            report, dsl = base_h.run(commands), args.commands
            report["provider"] = "DSL напрямую"
        elif args.cmd == "ask":
            report, dsl = analyze_text(_read_text(args), use_ai=not args.no_ai)
        else:
            repo = github_client.resolve_repo(args.repo)
            issue = github_client.get_issue(repo, args.number)
            report, dsl = analyze_text(f"{issue['title']}\n\n{issue['body']}", use_ai=not args.no_ai)
    except DSLError as exc:
        print(f"Ошибка DSL: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    except github_client.GitHubError as exc:
        print(f"GitHub: {exc}", file=sys.stderr)
        return 1

    if args.show_dsl:
        print("DSL:\n  " + "\n  ".join(dsl or ["(нет команд)"]), file=sys.stderr)
    body = to_markdown(report)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else body)

    if args.cmd == "issue" and args.post:
        try:
            url = github_client.post_comment(repo, args.number, body.replace("@", "@​"))
        except github_client.GitHubError as exc:
            print(f"GitHub: комментарий не опубликован: {exc}", file=sys.stderr)
            return 1
        print(f"Комментарий опубликован: {url}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
