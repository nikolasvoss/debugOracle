from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from debugoracle.readiness import _bounded_entries, collect_workspace_plan
from debugoracle.workspace_init_plan import (
    AutomaticInitInventory,
    plan_automatic_workspace_init,
)


class AutomaticWorkspaceInitPlannerTests(unittest.TestCase):
    def test_directory_entry_bound_stops_scandir_before_sorting(self) -> None:
        class _BoundedScandir:
            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, *args):  # type: ignore[no-untyped-def]
                return None

            def __iter__(self):  # type: ignore[no-untyped-def]
                yield type("Entry", (), {"path": "/workspace/b"})()
                yield type("Entry", (), {"path": "/workspace/a"})()
                raise AssertionError("directory traversal exceeded its hard bound")

        with (
            patch("debugoracle.readiness.MAX_DISCOVERY_FILES", 1),
            patch("debugoracle.readiness.os.scandir", return_value=_BoundedScandir()),
        ):
            selected, truncated = _bounded_entries(Path("/workspace"))

        self.assertEqual(selected, ())
        self.assertTrue(truncated)

    def test_empty_inventory_reports_fixed_unavailable_capabilities(self) -> None:
        inventory = AutomaticInitInventory(workspace_root="/workspace")

        plan = plan_automatic_workspace_init(inventory)

        self.assertEqual(plan.status, "failed")
        self.assertEqual(
            tuple(capability.name for capability in plan.capabilities),
            ("documentation", "debug_scaffold", "register_catalog"),
        )
        self.assertEqual(
            tuple(capability.status for capability in plan.capabilities),
            ("unavailable", "unavailable", "unavailable"),
        )

    def test_unique_discovered_inputs_produce_a_complete_provenance_plan(self) -> None:
        inventory = AutomaticInitInventory(
            workspace_root="/workspace",
            executable_candidates=("/workspace/build/app.elf",),
            svd_candidates=("/workspace/.dbgoracle/device.svd",),
            cortex_debug_openocd_configs=(
                (
                    "/workspace/openocd/interface.cfg",
                    "/workspace/openocd/target.cfg",
                ),
            ),
            documents=("/workspace/docs/vendor/reference.pdf",),
        )

        plan = plan_automatic_workspace_init(inventory, docs_authorized=True)

        self.assertEqual(plan.status, "complete")
        documentation, scaffold, registers = plan.capabilities
        self.assertEqual(documentation.status, "complete")
        self.assertEqual(documentation.inputs[0].provenance, "workspace_discovery")
        self.assertEqual(scaffold.status, "complete")
        self.assertEqual(
            tuple((item.key, item.provenance) for item in scaffold.inputs),
            (
                ("executable", "workspace_discovery"),
                ("openocd_configs", "cortex_debug_launch"),
            ),
        )
        self.assertEqual(registers.status, "complete")
        self.assertEqual(registers.inputs[0].provenance, "workspace_discovery")

    def test_explicit_then_workspace_configuration_precede_discovery(self) -> None:
        inventory = AutomaticInitInventory(
            workspace_root="/workspace",
            executable_candidates=("/workspace/build/discovered.elf",),
            configured_executable="/workspace/build/configured.elf",
            svd_candidates=("/workspace/.dbgoracle/discovered.svd",),
            configured_svd="/workspace/.dbgoracle/configured.svd",
            configured_openocd_configs=("/workspace/openocd/configured.cfg",),
            cortex_debug_openocd_configs=(("/workspace/openocd/launch.cfg",),),
        )

        configured_plan = plan_automatic_workspace_init(inventory)
        explicit_plan = plan_automatic_workspace_init(
            inventory,
            explicit_executable="/workspace/build/explicit.elf",
            explicit_svd="/workspace/.dbgoracle/explicit.svd",
            explicit_openocd_configs=("/workspace/openocd/explicit.cfg",),
        )

        configured_scaffold = configured_plan.capabilities[1]
        self.assertEqual(
            tuple(
                (item.values, item.provenance) for item in configured_scaffold.inputs
            ),
            (
                (("/workspace/build/configured.elf",), "workspace_setting"),
                (("/workspace/openocd/configured.cfg",), "workspace_setting"),
            ),
        )
        self.assertEqual(
            configured_plan.capabilities[2].inputs[0].values,
            ("/workspace/.dbgoracle/configured.svd",),
        )
        self.assertTrue(
            all(
                item.provenance == "explicit"
                for capability in explicit_plan.capabilities
                for item in capability.inputs
                if capability.name != "documentation"
            )
        )

    def test_ambiguities_and_actions_are_canonical_across_input_order(self) -> None:
        values = {
            "executable_candidates": (
                "/workspace/out/z.elf",
                "/workspace/build/a.elf",
            ),
            "svd_candidates": (
                "/workspace/.dbgoracle/z.svd",
                "/workspace/.dbgoracle/a.svd",
            ),
            "raw_openocd_configs": (
                "/workspace/openocd/target.cfg",
                "/workspace/openocd/interface.cfg",
            ),
            "cortex_debug_openocd_configs": (
                ("/workspace/openocd/second.cfg",),
                ("/workspace/openocd/first.cfg",),
            ),
            "documents": (
                "/workspace/docs/z.pdf",
                "/workspace/doc/a.pdf",
            ),
        }
        forward = plan_automatic_workspace_init(
            AutomaticInitInventory(workspace_root="/workspace", **values)
        )
        reverse = plan_automatic_workspace_init(
            AutomaticInitInventory(
                workspace_root="/workspace",
                executable_candidates=tuple(reversed(values["executable_candidates"])),
                svd_candidates=tuple(reversed(values["svd_candidates"])),
                raw_openocd_configs=tuple(reversed(values["raw_openocd_configs"])),
                cortex_debug_openocd_configs=tuple(
                    reversed(values["cortex_debug_openocd_configs"])
                ),
                documents=tuple(reversed(values["documents"])),
            )
        )

        self.assertEqual(forward.as_dict(), reverse.as_dict())
        self.assertEqual(forward.status, "partial")
        self.assertEqual(
            tuple(action.action_id for action in forward.capabilities[0].actions),
            ("authorize_document_ingest",),
        )
        self.assertEqual(
            tuple(item.key for item in forward.capabilities[1].ambiguities),
            ("executable", "openocd_configs"),
        )
        self.assertEqual(
            tuple(action.action_id for action in forward.capabilities[1].actions),
            ("choose_executable", "choose_openocd_configuration"),
        )
        self.assertEqual(
            tuple(action.action_id for action in forward.capabilities[2].actions),
            ("choose_svd",),
        )
        self.assertEqual(
            forward.capabilities[1].evidence[0].values,
            (
                "/workspace/openocd/interface.cfg",
                "/workspace/openocd/target.cfg",
            ),
        )

    def test_truncation_blocks_only_affected_discovery_not_higher_precedence(
        self,
    ) -> None:
        inventory = AutomaticInitInventory(
            workspace_root="/workspace",
            executable_candidates=("/workspace/build/discovered.elf",),
            configured_svd="/workspace/.dbgoracle/configured.svd",
            configured_openocd_configs=("/workspace/openocd/configured.cfg",),
            documents=("/workspace/docs/reference.pdf",),
            truncated_candidate_classes=(
                "documents",
                "executables",
                "svd_files",
                "cortex_debug_openocd_configs",
            ),
        )

        plan = plan_automatic_workspace_init(
            inventory,
            docs_authorized=True,
            explicit_executable="/workspace/build/explicit.elf",
        )

        documentation, scaffold, registers = plan.capabilities
        self.assertEqual(documentation.status, "partial")
        self.assertEqual(documentation.inputs, ())
        self.assertEqual(
            tuple(action.action_id for action in documentation.actions),
            ("resolve_truncated_documents",),
        )
        self.assertEqual(scaffold.status, "complete")
        self.assertEqual(registers.status, "complete")

    def test_workspace_plan_collects_one_normalized_automatic_init_inventory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            build = workspace / "build"
            dbgoracle = workspace / ".dbgoracle"
            vscode = workspace / ".vscode"
            docs = workspace / "docs" / "vendor"
            openocd = workspace / "openocd"
            for directory in (build, dbgoracle, vscode, docs, openocd):
                directory.mkdir(parents=True, exist_ok=True)
            executable = build / "app.elf"
            svd = dbgoracle / "device.svd"
            settings_cfg = openocd / "settings.cfg"
            launch_cfg = openocd / "launch.cfg"
            document = docs / "reference.pdf"
            for path in (executable, svd, settings_cfg, launch_cfg, document):
                path.write_bytes(b"fixture")
            raw_cfg = workspace / "raw.cfg"
            raw_cfg.write_bytes(b"fixture")
            (vscode / "settings.json").write_text(
                json.dumps(
                    {
                        "debugoracle.executable": "${workspaceFolder}/build/app.elf",
                        "debugoracle.svdFile": ".dbgoracle/device.svd",
                        "debugoracle.openocdConfigFiles": ["openocd/settings.cfg"],
                    }
                ),
                encoding="utf-8",
            )
            (vscode / "launch.json").write_text(
                json.dumps(
                    {
                        "configurations": [
                            {"type": "python", "configFiles": ["ignored.cfg"]},
                            {
                                "type": "cortex-debug",
                                "configFiles": ["openocd/launch.cfg"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            workspace_plan = collect_workspace_plan(workspace)
            inventory = workspace_plan.automatic_init_inventory

        self.assertEqual(
            set(workspace_plan.as_dict()),
            {
                "schema_version",
                "scope",
                "workspace_root",
                "status",
                "candidates",
                "truncated",
            },
        )
        self.assertEqual(inventory.workspace_root, str(workspace))
        self.assertEqual(inventory.executable_candidates, (str(executable),))
        self.assertEqual(inventory.svd_candidates, (str(svd),))
        self.assertEqual(inventory.raw_openocd_configs, (str(raw_cfg),))
        self.assertEqual(inventory.configured_executable, str(executable))
        self.assertEqual(inventory.configured_svd, str(svd))
        self.assertEqual(inventory.configured_openocd_configs, (str(settings_cfg),))
        self.assertEqual(inventory.cortex_debug_openocd_configs, ((str(launch_cfg),),))
        self.assertEqual(inventory.documents, (str(document),))

    def test_inventory_discovers_inputs_recursively_from_optional_input_folder(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            supplied = workspace / "debugoracle-input" / "manufacturer"
            supplied.mkdir(parents=True)
            executable = supplied / "firmware.elf"
            svd = supplied / "device.svd"
            document = supplied / "reference.pdf"
            config = supplied / "probe.cfg"
            for path in (executable, svd, document, config):
                path.write_bytes(b"fixture")

            inventory = collect_workspace_plan(workspace).automatic_init_inventory

        self.assertEqual(inventory.executable_candidates, (str(executable),))
        self.assertEqual(inventory.svd_candidates, (str(svd),))
        self.assertEqual(inventory.raw_openocd_configs, (str(config),))
        self.assertEqual(inventory.documents, (str(document),))

    def test_inventory_rejects_symlinked_and_outside_workspace_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = Path(tmpdir)
            workspace = sandbox / "workspace"
            outside = sandbox / "outside"
            vscode = workspace / ".vscode"
            dbgoracle = workspace / ".dbgoracle"
            docs = workspace / "docs"
            for directory in (vscode, dbgoracle, docs, outside):
                directory.mkdir(parents=True, exist_ok=True)
            real_elf = workspace / "real.elf"
            real_svd = workspace / "real.svd"
            real_cfg = workspace / "real.cfg"
            outside_pdf = outside / "outside.pdf"
            for path in (real_elf, real_svd, real_cfg, outside_pdf):
                path.write_bytes(b"fixture")
            linked_elf = workspace / "linked.elf"
            linked_svd = dbgoracle / "linked.svd"
            linked_cfg = workspace / "linked.cfg"
            linked_doc_dir = docs / "linked"
            linked_elf.symlink_to(real_elf)
            linked_svd.symlink_to(real_svd)
            linked_cfg.symlink_to(real_cfg)
            linked_doc_dir.symlink_to(outside, target_is_directory=True)
            (vscode / "settings.json").write_text(
                json.dumps(
                    {
                        "debugoracle.executable": "linked.elf",
                        "debugoracle.svdFile": ".dbgoracle/linked.svd",
                        "debugoracle.openocdConfigFiles": ["linked.cfg"],
                    }
                ),
                encoding="utf-8",
            )
            (vscode / "launch.json").write_text(
                json.dumps(
                    {
                        "configurations": [
                            {
                                "type": "cortex-debug",
                                "configFiles": ["linked.cfg"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            inventory = collect_workspace_plan(workspace).automatic_init_inventory

        self.assertEqual(inventory.configured_executable, None)
        self.assertEqual(inventory.configured_svd, None)
        self.assertEqual(inventory.configured_openocd_configs, ())
        self.assertEqual(inventory.cortex_debug_openocd_configs, ())
        self.assertEqual(inventory.svd_candidates, ())
        self.assertEqual(inventory.documents, ())

    def test_inventory_does_not_read_configuration_through_symlinked_vscode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = Path(tmpdir)
            workspace = sandbox / "workspace"
            outside_vscode = sandbox / "outside-vscode"
            workspace.mkdir()
            outside_vscode.mkdir()
            executable = workspace / "app.elf"
            config = workspace / "target.cfg"
            svd = workspace / "device.svd"
            for path in (executable, config, svd):
                path.write_bytes(b"fixture")
            (outside_vscode / "settings.json").write_text(
                json.dumps(
                    {
                        "debugoracle.executable": str(executable),
                        "debugoracle.svdFile": str(svd),
                        "debugoracle.openocdConfigFiles": [str(config)],
                    }
                ),
                encoding="utf-8",
            )
            (outside_vscode / "launch.json").write_text(
                json.dumps(
                    {
                        "configurations": [
                            {
                                "type": "cortex-debug",
                                "configFiles": [str(config)],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (workspace / ".vscode").symlink_to(outside_vscode, target_is_directory=True)

            inventory = collect_workspace_plan(workspace).automatic_init_inventory

        self.assertIsNone(inventory.configured_executable)
        self.assertIsNone(inventory.configured_svd)
        self.assertEqual(inventory.configured_openocd_configs, ())
        self.assertEqual(inventory.cortex_debug_openocd_configs, ())

    def test_document_entry_bound_blocks_selection_before_full_tree_walk(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            docs = workspace / "docs"
            docs.mkdir()
            (docs / "first.pdf").write_bytes(b"fixture")
            (docs / "second.pdf").write_bytes(b"fixture")

            with patch("debugoracle.readiness.MAX_DISCOVERY_FILES", 1):
                inventory = collect_workspace_plan(workspace).automatic_init_inventory
            plan = plan_automatic_workspace_init(inventory, docs_authorized=True)

        self.assertIn("documents", inventory.truncated_candidate_classes)
        self.assertEqual(plan.capabilities[0].status, "partial")
        self.assertEqual(plan.capabilities[0].inputs, ())

    def test_discovery_rejects_an_unreadable_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            build = workspace / "build"
            build.mkdir()
            executable = build / "app.elf"
            executable.write_bytes(b"ELF")
            executable.chmod(0)

            inventory = collect_workspace_plan(workspace).automatic_init_inventory

        self.assertEqual(inventory.executable_candidates, ())

    def test_inventory_bounds_each_candidate_class_and_blocks_auto_selection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            for directory in (
                workspace / "build",
                workspace / ".dbgoracle",
                workspace / "docs",
            ):
                directory.mkdir(parents=True)
            for name in ("a", "b"):
                (workspace / "build" / f"{name}.elf").write_bytes(b"fixture")
                (workspace / ".dbgoracle" / f"{name}.svd").write_bytes(b"fixture")
                (workspace / "docs" / f"{name}.pdf").write_bytes(b"fixture")
                (workspace / f"{name}.cfg").write_bytes(b"fixture")

            with patch("debugoracle.readiness.MAX_DISCOVERY_CANDIDATES", 1):
                inventory = collect_workspace_plan(workspace).automatic_init_inventory
            plan = plan_automatic_workspace_init(inventory, docs_authorized=True)

        self.assertEqual(len(inventory.executable_candidates), 1)
        self.assertEqual(len(inventory.svd_candidates), 1)
        self.assertEqual(len(inventory.raw_openocd_configs), 1)
        self.assertEqual(len(inventory.documents), 1)
        self.assertEqual(
            inventory.truncated_candidate_classes,
            ("documents", "executables", "raw_openocd_configs", "svd_files"),
        )
        self.assertEqual(
            tuple(capability.status for capability in plan.capabilities),
            ("partial", "partial", "partial"),
        )
        self.assertEqual(plan.capabilities[0].inputs, ())
        self.assertEqual(plan.capabilities[2].inputs, ())

    def test_two_cortex_debug_launches_remain_ambiguous_even_when_lists_match(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            vscode = workspace / ".vscode"
            vscode.mkdir()
            config = workspace / "board.cfg"
            config.write_bytes(b"fixture")
            repeated = {"type": "cortex-debug", "configFiles": ["board.cfg"]}
            (vscode / "launch.json").write_text(
                json.dumps({"configurations": [repeated, repeated]}),
                encoding="utf-8",
            )

            inventory = collect_workspace_plan(workspace).automatic_init_inventory
            plan = plan_automatic_workspace_init(inventory)

        self.assertEqual(len(inventory.cortex_debug_openocd_configs), 2)
        self.assertEqual(
            tuple(item.key for item in plan.capabilities[1].ambiguities),
            ("openocd_configs",),
        )

    def test_document_inventory_ignores_generated_sidecar_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            docs = workspace / "docs"
            sidecar = docs / "reference.pdf.dbgoracle-docs"
            sidecar.mkdir(parents=True)
            source = docs / "reference.pdf"
            source.write_bytes(b"fixture")
            (sidecar / "generated.pdf").write_bytes(b"fixture")

            inventory = collect_workspace_plan(workspace).automatic_init_inventory

        self.assertEqual(inventory.documents, (str(source),))

    def test_pure_planner_performs_no_filesystem_io(self) -> None:
        inventory = AutomaticInitInventory(
            workspace_root="/workspace",
            executable_candidates=("/workspace/build/app.elf",),
            svd_candidates=("/workspace/.dbgoracle/device.svd",),
            cortex_debug_openocd_configs=(("/workspace/board.cfg",),),
            documents=("/workspace/docs/reference.pdf",),
        )

        with (
            patch("builtins.open", side_effect=AssertionError("file opened")),
            patch("os.scandir", side_effect=AssertionError("directory scanned")),
            patch("pathlib.Path.resolve", side_effect=AssertionError("path resolved")),
            patch("pathlib.Path.stat", side_effect=AssertionError("path stated")),
        ):
            plan = plan_automatic_workspace_init(inventory, docs_authorized=True)

        self.assertEqual(plan.status, "complete")


if __name__ == "__main__":
    unittest.main()
