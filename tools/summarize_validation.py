"""Summarize recorded human judgments; this does not grade model outputs."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rubric = json.loads((root / "tests/rubric.json").read_text())
outputs = json.loads((root / "tests/results/forward-outputs.json").read_text())
checks = json.loads((root / "tests/results/assessment.json").read_text())["checks"]
expected = {(case, index) for case, items in rubric.items()
            for index in range(1, len(items) + 1)}
actual = {(row["case_id"], row["criterion_index"]) for row in checks}
assert actual == expected and len(checks) == len(expected), "Missing or duplicate checks"
assert {row["id"] for row in outputs} == set(rubric), "Missing outputs"
assert len(outputs) == len(rubric), "Duplicate outputs"
for row in checks:
    assert row["criterion"] == rubric[row["case_id"]][row["criterion_index"] - 1]
    assert row["verdict"] in {"pass", "fail"} and row["evidence"].strip()
passed = sum(row["verdict"] == "pass" for row in checks)
failed_cases = {row["case_id"] for row in checks if row["verdict"] == "fail"}
print(f"Recorded checks: {passed}/{len(checks)} pass; {len(checks)-passed} fail")
print(f"All-checks-pass cases: {len(rubric)-len(failed_cases)}/{len(rubric)}")
print("These are prompt behavior checks, not image quality measurements.")
