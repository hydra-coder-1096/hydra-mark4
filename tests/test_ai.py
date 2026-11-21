import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import ai
import main
from hydra_dsl import parse_command

PY_TRACE = """Запускаю бота и падает:
Traceback (most recent call last):
  File "/workspaces/hydra-mark4/main.py", line 3, in <module>
    import requests
  File "/usr/lib/python3.12/site-packages/x.py", line 1, in <module>
ModuleNotFoundError: No module named 'requests'
"""

JS_TRACE = """Uncaught TypeError: Cannot read properties of undefined (reading 'map')
    at App (src/App.js:12:5)
    at node_modules/react/index.js:1:1"""


class TestRules(unittest.TestCase):
    def test_python_traceback(self):
        lines = ai.rules_translate(PY_TRACE)
        first = parse_command(lines[0])
        self.assertEqual(first["operation"], "ANALYZE")
        self.assertEqual(first["target"], "python")
        self.assertEqual(first["params"]["error"], "ModuleNotFoundError")
        self.assertEqual(first["params"]["message"], "No module named 'requests'")
        self.assertEqual(first["params"]["file"], "/workspaces/hydra-mark4/main.py")
        self.assertEqual(first["params"]["line"], "3")
        self.assertEqual(len(lines), 1)

    def test_name_error_adds_search(self):
        lines = ai.rules_translate("NameError: name 'greet' is not defined. Did you mean: 'great'?")
        self.assertEqual(parse_command(lines[1])["params"]["query"], "greet")

    def test_js_traceback(self):
        first = parse_command(ai.rules_translate(JS_TRACE)[0])
        self.assertEqual(first["target"], "javascript")
        self.assertEqual(first["params"]["file"], "src/App.js")

    def test_no_error(self):
        lines = ai.rules_translate("Не работает функция `analyze_text` в файле main.py")
        ops = [parse_command(x)["operation"] for x in lines]
        self.assertEqual(ops, ["INSPECT", "SEARCH"])

    def test_plain_text(self):
        first = parse_command(ai.rules_translate("всё сломалось")[0])
        self.assertEqual(first["target"], "unknown")


NO_KEYS = {"GEMINI_API_KEY": "", "OPENAI_API_KEY": "", "HYDRA_AI_PROVIDER": "", "HYDRA_MODEL": ""}


def gemini_reply(text):
    """Фейковый ответ urlopen с телом generateContent."""
    body = {"candidates": [{"content": {"parts": [{"text": "думаю...", "thought": True}, {"text": text}]}}]}
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(body).encode("utf-8")
    return response


class TestTranslate(unittest.TestCase):
    def test_auto_without_keys(self):
        with mock.patch.dict(os.environ, NO_KEYS):
            commands, info = ai.translate(PY_TRACE)
        self.assertEqual(info["provider"], "rules")
        self.assertIn("GEMINI_API_KEY", info["warnings"][0])
        self.assertEqual(commands[0]["operation"], "ANALYZE")

    def test_auto_prefers_gemini(self):
        with mock.patch.dict(os.environ, {**NO_KEYS, "GEMINI_API_KEY": "g", "OPENAI_API_KEY": "o"}):
            self.assertEqual(ai._pick_provider(None), "gemini")
        with mock.patch.dict(os.environ, {**NO_KEYS, "OPENAI_API_KEY": "o"}):
            self.assertEqual(ai._pick_provider(None), "openai")

    def test_gemini_request(self):
        answer = "```\nANALYZE python error=NameError message=\"name 'x' is not defined\"\nSEARCH project query=x\n```"
        with mock.patch.dict(os.environ, {**NO_KEYS, "GEMINI_API_KEY": " AQ.test "}), \
                mock.patch("ai.urllib.request.urlopen", return_value=gemini_reply(answer)) as urlopen:
            commands, info = ai.translate(PY_TRACE)
        request = urlopen.call_args[0][0]
        self.assertIn("/models/gemini-3.5-flash-lite:generateContent", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "AQ.test")
        sent = json.loads(request.data)
        self.assertIn("Hydra DSL", sent["system_instruction"]["parts"][0]["text"])
        self.assertIn("ModuleNotFoundError", sent["contents"][0]["parts"][0]["text"])
        self.assertEqual(info["provider"], "gemini/gemini-3.5-flash-lite")
        self.assertEqual([c["operation"] for c in commands], ["ANALYZE", "SEARCH"])

    def test_gemini_model_override(self):
        with mock.patch.dict(os.environ, {**NO_KEYS, "GEMINI_API_KEY": "k", "HYDRA_MODEL": "gemini-3.8-flash"}), \
                mock.patch("ai.urllib.request.urlopen", return_value=gemini_reply("SEARCH project query=x")) as urlopen:
            _, info = ai.translate("x")
        self.assertIn("/models/gemini-3.8-flash:", urlopen.call_args[0][0].full_url)
        self.assertEqual(info["provider"], "gemini/gemini-3.8-flash")

    def test_gemini_http_error_falls_back(self):
        error = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b'{"error":"bad key"}'))
        with mock.patch.dict(os.environ, {**NO_KEYS, "GEMINI_API_KEY": "k"}), \
                mock.patch("ai.urllib.request.urlopen", side_effect=error):
            commands, info = ai.translate(PY_TRACE)
        self.assertEqual(info["provider"], "rules")
        self.assertIn("Gemini HTTP 401", info["warnings"][0])
        self.assertEqual(commands[0]["params"]["error"], "ModuleNotFoundError")

    def test_openai_failure_falls_back(self):
        with mock.patch.dict(ai.CALLERS, {"openai": mock.Mock(side_effect=RuntimeError("boom"))}):
            _, info = ai.translate(PY_TRACE, provider="openai")
        self.assertEqual(info["provider"], "rules")
        self.assertIn("boom", info["warnings"][0])

    def test_openai_success(self):
        fake = mock.Mock(return_value=[parse_command("ANALYZE python error=NameError")])
        with mock.patch.dict(os.environ, NO_KEYS), mock.patch.dict(ai.CALLERS, {"openai": fake}):
            _, info = ai.translate("x", provider="openai")
        self.assertEqual(info["provider"], "openai/gpt-5.6-terra")
        self.assertEqual(info["dsl"], ["ANALYZE python error=NameError"])

    def test_empty(self):
        commands, info = ai.translate("   ")
        self.assertEqual(commands, [])


class TestDotenv(unittest.TestCase):
    def test_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".env")
            with open(path, "w", encoding="utf-8") as f:
                f.write("# c\nGEMINI_API_KEY=\"AQ.x\"\nexport HYDRA_MODEL=m\nSET_ALREADY=new\n")
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "SET_ALREADY": "old"}):
                main.load_dotenv(path)
                self.assertEqual(os.environ["GEMINI_API_KEY"], "AQ.x")
                self.assertEqual(os.environ["HYDRA_MODEL"], "m")
                self.assertEqual(os.environ["SET_ALREADY"], "old")


if __name__ == "__main__":
    unittest.main()
