#!/usr/bin/env python3
"""
Unit tests validating the GitHub Actions CI/CD workflow (.github/workflows/build-ipa.yml).
Ensures compliance with R4:
- macos-14 / macos-15 runner
- XcodeGen installation & project generation
- Building both TrollStore and Sideload configurations
- Packaging unsigned / ad-hoc signed IPAs
- Uploading IPAs as workflow artifacts
"""

import unittest
from pathlib import Path
import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent


class TestGitHubActionsWorkflow(unittest.TestCase):
    """Validates CI/CD workflow YAML structure and steps."""

    @classmethod
    def setUpClass(cls):
        cls.workflow_path = WORKSPACE_ROOT / ".github" / "workflows" / "build-ipa.yml"
        if not cls.workflow_path.exists():
            raise FileNotFoundError(f"Missing workflow file at {cls.workflow_path}")
        with open(cls.workflow_path, "r", encoding="utf-8") as f:
            cls.workflow = yaml.safe_load(f)

    def test_workflow_triggers(self):
        # PyYAML may parse 'on' as boolean True or string 'on'
        triggers = self.workflow.get("on") or self.workflow.get(True)
        self.assertIsNotNone(triggers, "Workflow must declare trigger events")
        self.assertIn("push", triggers)
        self.assertIn("workflow_dispatch", triggers)

    def test_job_runner(self):
        jobs = self.workflow.get("jobs", {})
        self.assertTrue(len(jobs) > 0, "Workflow must declare at least one job")
        job = list(jobs.values())[0]
        runner = job.get("runs-on")
        self.assertIn(runner, ["macos-14", "macos-15"], "Runner must be Apple Silicon macos-14 or macos-15")

    def test_pipeline_steps(self):
        jobs = self.workflow.get("jobs", {})
        job = list(jobs.values())[0]
        steps = job.get("steps", [])
        self.assertTrue(len(steps) >= 6, "Job should contain all required pipeline steps")

        # Collect step names and run commands
        step_names = [s.get("name", "") for s in steps]
        step_runs = " ".join([s.get("run", "") for s in steps])
        step_uses = " ".join([s.get("uses", "") for s in steps])

        # Step 1: Checkout
        self.assertIn("actions/checkout", step_uses)

        # Step 2: Install XcodeGen
        self.assertIn("xcodegen", step_runs.lower())

        # Step 3: Generate Xcode project
        self.assertIn("xcodegen generate", step_runs)

        # Step 4: xcodebuild archive
        self.assertIn("xcodebuild archive", step_runs)
        self.assertIn("DeskSimulator-TrollStore", step_runs)
        self.assertIn("DeskSimulator-Sideload", step_runs)

        # Step 5: Packaging IPAs
        self.assertIn("DeskSimulator-TrollStore.ipa", step_runs)
        self.assertIn("DeskSimulator-Sideload.ipa", step_runs)

        # Step 6: Artifact upload
        self.assertIn("actions/upload-artifact", step_uses)


if __name__ == "__main__":
    unittest.main()
