import tempfile
import unittest
from pathlib import Path

from base_h import execute, run
from hydra_dsl import parse_command


class TestBaseH(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "main.py").write_text("import requests\nfrom helpers import greet\nprint(greet(name))\n")
        (self.root / "helpers.py").write_text("def greet(who):\n    return 'hi ' + who\n")
        (self.root / "random.py").write_text("x = 1\n")
        (self.root / "requirements.txt").write_text("openai>=1.66\n")
        (self.root / ".env").write_text("OPENAI_API_KEY=secret\n")
        (self.root / "broken.py").write_text("def f():\n    return 1\nEOF\n")

    def tearDown(self):
        self.tmp.cleanup()

    def ex(self, line):
        return execute(parse_command(line), root=self.root)

    def test_legacy_check(self):
        r = self.ex("ANALYZE python error=ModuleNotFoundError")
        self.assertEqual((r["status"], r["operation"], r["target"], r["params"]),
                         ("ok", "ANALYZE", "python", {"error": "ModuleNotFoundError"}))

    def test_module_not_found(self):
        r = self.ex("ANALYZE python error=ModuleNotFoundError message=\"No module named 'requests'\" file=main.py line=1")
        self.assertTrue(r["known"])
        self.assertIn("import requests", r["where"]["snippet"])
        self.assertTrue(any("pip install requests" in s for s in r["how_to_fix"]))

    def test_module_in_requirements(self):
        r = self.ex("ANALYZE python error=ModuleNotFoundError message=\"No module named 'openai'\"")
        self.assertTrue(any("pip install -r requirements.txt" in s for s in r["how_to_fix"]))

    def test_name_error_definition(self):
        r = self.ex("ANALYZE python error=NameError message=\"name 'greet' is not defined\" file=main.py line=3")
        self.assertTrue(any("from helpers import greet" in s for s in r["how_to_fix"]))

    def test_name_error_unknown(self):
        r = self.ex("ANALYZE python error=NameError message=\"name 'name' is not defined\"")
        self.assertTrue(any("нигде в проекте не определено" in s for s in r["how_to_fix"]))

    def test_shadowed_module(self):
        r = self.ex("ANALYZE python error=AttributeError message=\"module 'random' has no attribute 'randint'\"")
        self.assertIn("random.py", r["why"])

    def test_terminal_garbage(self):
        r = self.ex("ANALYZE python error=SyntaxError message=\"invalid syntax\" file=broken.py line=3")
        self.assertIn("команду терминала", r["how_to_fix"][0])

    def test_absolute_traceback_path(self):
        r = self.ex(f"ANALYZE python error=NameError file=/home/runner/work/x/x/main.py line=3")
        self.assertEqual(r["where"]["file"], "main.py")

    def test_search(self):
        r = self.ex('SEARCH project query="greet"')
        self.assertEqual(r["status"], "ok")
        self.assertEqual({h["file"] for h in r["hits"]}, {"main.py", "helpers.py"})

    def test_search_skips_env(self):
        r = self.ex("SEARCH project query=secret")
        self.assertEqual(r["total"], 0)

    def test_inspect(self):
        r = self.ex("INSPECT file path=helpers.py line=2 context=0")
        self.assertEqual(r["snippet"], "> 2 |     return 'hi ' + who")

    def test_inspect_blocked(self):
        for path in ("../../etc/passwd", "/etc/passwd", ".env"):
            self.assertEqual(self.ex(f"INSPECT file path={path}")["status"], "error", path)

    def test_unknown_operation(self):
        r = self.ex("DELETE file path=main.py")
        self.assertEqual(r["status"], "error")

    def test_run_report(self):
        commands = [parse_command("ANALYZE python error=ModuleNotFoundError "
                                  "message=\"No module named 'requests'\" file=main.py line=1"),
                    parse_command("SEARCH project query=requests")]
        report = run(commands, root=self.root)
        self.assertEqual(report["confidence"], "high")
        self.assertEqual(report["where"][0]["file"], "main.py")
        self.assertEqual(report["errors"], [])

    def test_run_empty(self):
        report = run([], root=self.root)
        self.assertEqual(report["confidence"], "low")


if __name__ == "__main__":
    unittest.main()
