# hydra-mark4 (Прот4)

Помощник для GitHub: читает issue или текст ошибки, находит вероятную причину, место в коде и способ исправить.
Код сам не меняет.

```
текст / issue ──► AI Base (ai.py) ──► Hydra DSL ──► Base H (base_h.py) ──► отчёт / комментарий
                  Gemini / OpenAI / правила         локально, без AI
```

## Структура

```
hydra-mark4/
├── .github/workflows/hydra.yml   авто-разбор новых issue
├── tests/                        test_dsl.py, test_base_h.py, test_ai.py
├── main.py                       точка входа (CLI)
├── ai.py                         AI Base: текст -> команды DSL
├── hydra_dsl.py                  парсер и сборщик DSL
├── base_h.py                     Base H: выполнение DSL
├── github_client.py              GitHub API: issue и комментарии
├── requirements.txt
└── .gitignore
```

## Установка

```bash
pip install -r requirements.txt
python -m unittest discover -s tests
```

Ключи — только в переменных окружения: секрет Codespaces / Actions или файл `.env` в корне
(он в `.gitignore`, в git не попадает). Без ключа всё работает на правилах.

| Переменная | Зачем | По умолчанию |
|---|---|---|
| `GEMINI_API_KEY` | ключ Gemini (Google AI Studio) | — |
| `OPENAI_API_KEY` | ключ OpenAI (если нужен он) | — |
| `HYDRA_AI_PROVIDER` | `auto`, `gemini`, `openai` или `rules` | `auto`: Gemini → OpenAI → правила |
| `HYDRA_MODEL` | модель выбранного провайдера | `gemini-3.5-flash-lite` / `gpt-5.6-terra` |
| `GITHUB_TOKEN` | доступ к issue | есть в Codespaces и Actions |

## Команды

```bash
python main.py ask "ModuleNotFoundError: No module named 'requests'"
python main.py ask -f error.log
python main.py run "ANALYZE python error=NameError message=\"name 'x' is not defined\" file=main.py line=3"
python main.py issue 12             # только показать
python main.py issue 12 --post      # опубликовать комментарий
```

Флаги: `--json` (сырой JSON), `--no-ai` (без AI), `--show-dsl` (показать команды DSL).

## Hydra DSL

`<OPERATION> <TARGET> [key=value ...]`, значения с пробелами — в двойных кавычках.

| Команда | Что делает |
|---|---|
| `ANALYZE <python\|javascript\|unknown> error=Тип message="..." file="путь" line=N` | причина и шаги исправления |
| `SEARCH <project\|logs> query="текст"` | поиск по файлам проекта (`logs` — по .log/.out/.txt) |
| `INSPECT file path="путь" line=N context=N` | кусок файла вокруг строки |

Base H не читает файлы вне проекта, `.env*`, ключи (`.pem`, `.key`) и папку `.git`.

## Авто-комментарии в issue

1. Settings → Secrets and variables → Actions → New repository secret: `GEMINI_API_KEY` (необязательно).
2. Новый issue → Actions запускает `hydra.yml` → в issue появляется комментарий.
3. Повторный запуск вручную: Actions → Hydra → Run workflow → номер issue.
