from pathlib import Path
import unittest


class ModuleSpecRegistryTests(unittest.TestCase):
    def test_every_top_level_debugoracle_module_has_matching_spec(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        module_dir = repo_root / "debugoracle"
        specs_dir = repo_root / "docs" / "specs"

        ignored = {"__init__", "__main__"}
        modules = {
            path.stem
            for path in module_dir.glob("*.py")
            if path.stem not in ignored
        }
        specs = {
            path.stem
            for path in specs_dir.glob("*.md")
            if path.stem != "README"
        }

        self.assertEqual(modules, specs)
