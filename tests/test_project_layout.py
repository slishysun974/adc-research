from __future__ import annotations

import unittest
from pathlib import Path


class ProjectLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]

    def test_governance_files_exist(self) -> None:
        for relative in (
            "docs/PROJECT_CHARTER.md",
            "docs/STATUS.md",
            "docs/DECISIONS.md",
        ):
            self.assertTrue((self.root / relative).is_file(), relative)

    def test_research_modules_are_separated(self) -> None:
        package = self.root / "src" / "adc_research"
        for module in ("common", "platform", "theory", "calibration", "metrics"):
            self.assertTrue((package / module / "__init__.py").is_file(), module)

    def test_theory_does_not_import_experimental_platform(self) -> None:
        theory_root = self.root / "src" / "adc_research" / "theory"
        forbidden = ("adc_research.platform", "..platform", "from platform")
        for source in theory_root.rglob("*.py"):
            contents = source.read_text(encoding="utf-8")
            self.assertFalse(
                any(pattern in contents for pattern in forbidden),
                f"Theory/platform boundary violated by {source}",
            )

    def test_pre_charter_prototype_is_archived(self) -> None:
        archive = self.root / "legacy" / "pre_charter_v0_1"
        self.assertTrue((archive / "src" / "adc_research" / "pipeline.py").is_file())
        self.assertTrue((archive / "results" / "experiment_001_baseline.json").is_file())


if __name__ == "__main__":
    unittest.main()

