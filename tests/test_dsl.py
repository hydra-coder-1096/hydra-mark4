import unittest

from hydra_dsl import DSLError, build_command, parse_command, parse_lines


class TestDSL(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(parse_command("ANALYZE python error=ModuleNotFoundError"),
                         {"operation": "ANALYZE", "target": "python", "params": {"error": "ModuleNotFoundError"}})

    def test_quotes_and_spaces(self):
        cmd = parse_command("""SEARCH project query="где используется analyze_text" message="No module named 'x'" """)
        self.assertEqual(cmd["params"]["query"], "где используется analyze_text")
        self.assertEqual(cmd["params"]["message"], "No module named 'x'")

    def test_empty(self):
        self.assertIsNone(parse_command(""))
        self.assertIsNone(parse_command("   "))

    def test_bad_quote(self):
        with self.assertRaises(DSLError):
            parse_command('SEARCH project query="без конца')

    def test_roundtrip(self):
        params = {"message": 'a "b" \\ c \'d\'', "line": 7}
        cmd = parse_command(build_command("ANALYZE", "python", params))
        self.assertEqual(cmd["params"], {"message": 'a "b" \\ c \'d\'', "line": "7"})

    def test_parse_lines(self):
        text = "```\nANALYZE python error=NameError\nвот команды:\n1. SEARCH project query=x\n```"
        commands, rejected = parse_lines(text)
        self.assertEqual([c["operation"] for c in commands], ["ANALYZE", "SEARCH"])
        self.assertEqual(rejected, ["вот команды:"])


if __name__ == "__main__":
    unittest.main()
