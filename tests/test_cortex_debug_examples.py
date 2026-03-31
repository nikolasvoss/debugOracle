import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS_EXAMPLE = ROOT / "examples" / "cortex-debug" / "tasks.json.example"
README_EXAMPLE = ROOT / "examples" / "cortex-debug" / "README.md"
LAUNCH_EXAMPLE = ROOT / "examples" / "cortex-debug" / "launch.jsonc.example"
AGENT_INSTRUCTIONS = ROOT / "examples" / "cortex-debug" / "AGENT_INSTRUCTIONS.md"


class CortexDebugExampleTests(unittest.TestCase):
    def _tasks_by_label(self) -> dict[str, dict[str, object]]:
        tasks_doc = json.loads(TASKS_EXAMPLE.read_text(encoding="utf-8"))
        return {task["label"]: task for task in tasks_doc["tasks"]}

    def test_tasks_use_run_and_stop_contract(self) -> None:
        tasks = self._tasks_by_label()
        start_cmd = tasks["DebugOracle: Start RTT run"]["command"]
        stop_cmd = tasks["DebugOracle: Stop RTT run"]["command"]

        self.assertIn("dbgoracle run --detach", start_cmd)
        self.assertIn("--workspace-root", start_cmd)
        self.assertIn("--connect-timeout 30", start_cmd)
        self.assertIn("--output", start_cmd)
        self.assertIn("--state-out", start_cmd)
        self.assertIn("dbgoracle stop --workspace-root", stop_cmd)

    def test_prelaunch_depends_on_prepare_and_start(self) -> None:
        tasks = self._tasks_by_label()
        prelaunch = tasks["DebugOracle: Prelaunch"]
        self.assertEqual(
            prelaunch["dependsOn"],
            [
                "Prepare debug logs",
                "DebugOracle: Guard Attach Launch",
                "DebugOracle: Start RTT run",
            ],
        )

    def test_launch_example_wires_prelaunch_and_postdebug_tasks(self) -> None:
        launch = LAUNCH_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn('"name": "DebugOracle: Attach STM32"', launch)
        self.assertIn('"debugoracleRole": "golden-path-attach"', launch)
        self.assertIn('"preLaunchTask": "DebugOracle: Prelaunch"', launch)
        self.assertIn('"postDebugTask": "DebugOracle: Stop RTT run"', launch)
        self.assertIn('// "monitor rtt setup', launch)
        self.assertIn(
            '// "monitor rtt server start ${config:debugoracle.rttPort} 0"', launch
        )

    def test_readme_documents_run_stop_workflow(self) -> None:
        readme = README_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("## Which command when?", readme)
        self.assertIn(
            "dbgoracle init-workspace --workspace-root . --executable build/app.elf --attach",
            readme,
        )
        self.assertIn("DebugOracle: Attach STM32", readme)
        self.assertIn("Golden Path: prepared", readme)
        self.assertIn("dbgoracle run --detach", readme)
        self.assertIn("dbgoracle stop --workspace-root .", readme)
        self.assertIn("Do not stack this on top of `make debug`", readme)

    def test_find_tcl_port_subcommand_is_documented(self) -> None:
        readme = README_EXAMPLE.read_text(encoding="utf-8")
        agent_instructions = AGENT_INSTRUCTIONS.read_text(encoding="utf-8")

        self.assertIn(
            "dbgoracle find-tcl-port --workspace-root . --print-fetch", readme
        )
        self.assertIn(
            "dbgoracle find-tcl-port --workspace-root . --print-fetch",
            agent_instructions,
        )


if __name__ == "__main__":
    unittest.main()
