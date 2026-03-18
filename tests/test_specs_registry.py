from pathlib import Path
import unittest


class ModuleSpecRegistryTests(unittest.TestCase):
    def test_spec_registry_entries_point_to_existing_code_and_spec_files(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        registry = (repo_root / "docs" / "specs" / "README.md").read_text(encoding="utf-8")

        entries: list[tuple[str, str, str]] = []
        for line in registry.splitlines():
            if not line.startswith("| `"):
                continue
            columns = [part.strip() for part in line.strip("|").split("|")]
            if len(columns) != 3:
                continue
            module = columns[0].strip("`")
            code_path = columns[1].strip("`")
            spec_cell = columns[2]
            spec_name = spec_cell.split("](")[-1].rstrip(")")
            entries.append((module, code_path, spec_name))

        modules = {module for module, _, _ in entries}
        self.assertNotIn("models", modules)
        self.assertNotIn("output", modules)

        for _, code_path, spec_name in entries:
            self.assertTrue((repo_root / code_path).is_file(), code_path)
            self.assertTrue((repo_root / "docs" / "specs" / spec_name).is_file(), spec_name)
