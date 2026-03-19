import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS_EXAMPLE = ROOT / "examples" / "cortex-debug" / "tasks.json.example"
README_EXAMPLE = ROOT / "examples" / "cortex-debug" / "README.md"
LAUNCH_EXAMPLE = ROOT / "examples" / "cortex-debug" / "launch.jsonc.example"


def _tasks_by_label():
    tasks_doc = json.loads(TASKS_EXAMPLE.read_text(encoding="utf-8"))
    return {task["label"]: task for task in tasks_doc["tasks"]}


def test_tasks_use_run_and_stop_contract():
    tasks = _tasks_by_label()
    start_cmd = tasks["DebugOracle: Start RTT run"]["command"]
    stop_cmd = tasks["DebugOracle: Stop RTT run"]["command"]

    assert "dbgoracle run --detach" in start_cmd
    assert "--workspace-root" in start_cmd
    assert "--connect-timeout 30" in start_cmd
    assert "--output" in start_cmd
    assert "--state-out" in start_cmd
    assert "dbgoracle stop --workspace-root" in stop_cmd


def test_prelaunch_depends_on_prepare_and_start():
    tasks = _tasks_by_label()
    prelaunch = tasks["DebugOracle: Prelaunch"]
    assert prelaunch["dependsOn"] == ["Prepare debug logs", "DebugOracle: Start RTT run"]


def test_launch_example_wires_prelaunch_and_postdebug_tasks():
    launch = LAUNCH_EXAMPLE.read_text(encoding="utf-8")
    assert '"preLaunchTask": "DebugOracle: Prelaunch"' in launch
    assert '"postDebugTask": "DebugOracle: Stop RTT run"' in launch
    assert '// "monitor rtt setup' in launch
    assert '// "monitor rtt server start 60001 0"' in launch


def test_readme_documents_run_stop_workflow():
    readme = README_EXAMPLE.read_text(encoding="utf-8")
    assert "## Which command when?" in readme
    assert "./dbgoracle run --detach" in readme
    assert "./dbgoracle stop --workspace-root ." in readme
