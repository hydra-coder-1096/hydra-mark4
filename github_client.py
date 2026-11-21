"""GitHub REST API: чтение issue и публикация комментария. Только стандартная библиотека.

Токен: GITHUB_TOKEN (есть в Codespaces и GitHub Actions) или GH_TOKEN.
Репозиторий: --repo owner/name или GITHUB_REPOSITORY.
"""
import json
import os
import re
import urllib.error
import urllib.request

API = "https://api.github.com"
HINTS = {401: "токен неверный или истёк", 403: "у токена нет прав (нужно Issues: write)",
         404: "репозиторий или issue не найден, либо нет доступа"}


class GitHubError(RuntimeError):
    pass


def _token():
    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    if not token:
        raise GitHubError("GITHUB_TOKEN не найден")
    return token


def _request(method, path, data=None):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Authorization": f"Bearer {_token()}", "Accept": "application/vnd.github+json",
               "User-Agent": "hydra-mark4"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(API + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise GitHubError(f"HTTP {exc.code}: {HINTS.get(exc.code, '')} {detail}".strip()) from None
    except urllib.error.URLError as exc:
        raise GitHubError(f"нет связи с GitHub: {exc.reason}") from None


def resolve_repo(repo=None):
    repo = (repo or os.environ.get("GITHUB_REPOSITORY", "")).strip()
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise GitHubError("укажи репозиторий: --repo owner/name")
    return repo


def get_issue(repo, number):
    data = _request("GET", f"/repos/{repo}/issues/{int(number)}")
    return {"number": data.get("number", int(number)), "title": data.get("title") or "",
            "body": data.get("body") or "", "url": data.get("html_url", "")}


def post_comment(repo, number, body):
    data = _request("POST", f"/repos/{repo}/issues/{int(number)}/comments", {"body": body})
    return data.get("html_url", "")
