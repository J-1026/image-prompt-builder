"""Exercise pixel invariants and failure conditions with synthetic images."""
import importlib.util
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "protected_region", ROOT / "skills/image-prompt-builder/scripts/protected_region.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProtectedRegionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = Image.new("RGB", (8, 6), (10, 20, 30))
        self.candidate = Image.new("RGB", (8, 6), (110, 120, 130))
        self.mask = Image.new("L", (8, 6), 0)
        self.mask.paste(255, (0, 3, 8, 6))
        for name, im in (("base", self.base), ("candidate", self.candidate), ("mask", self.mask)):
            im.save(self.root / f"{name}.png")

    def args(self, command="composite"):
        return Namespace(command=command, base=self.root/"base.png",
                         candidate=self.root/"candidate.png", mask=self.root/"mask.png",
                         output=self.root/"final.png" if command == "composite" else None,
                         report=self.root/"report.json")

    def test_detects_protected_drift(self):
        report = MODULE.audit(self.base, self.candidate, self.mask)
        self.assertEqual(report["protected_pixels"], 24)
        self.assertEqual(report["changed_protected_pixels"], 24)
        self.assertFalse(report["exact_match"])
        with redirect_stdout(StringIO()):
            self.assertEqual(MODULE.run(self.args("audit")), 1)

    def test_composite_preserves_base_and_keeps_requested_edit(self):
        self.mask.putpixel((0, 2), 128)
        self.mask.save(self.root/"mask.png")
        with redirect_stdout(StringIO()):
            self.assertEqual(MODULE.run(self.args()), 0)
        with Image.open(self.root/"final.png") as result:
            self.assertEqual(result.getpixel((0, 4)), (10, 20, 30))
            self.assertEqual(result.getpixel((0, 0)), (110, 120, 130))
            self.assertEqual(result.getpixel((0, 2)), (60, 70, 80))
            self.assertTrue(MODULE.audit(self.base, result, self.mask)["exact_match"])

    def test_rgba_alpha_drift_is_not_ignored(self):
        a = Image.new("RGBA", (8, 6), (10, 20, 30, 0))
        b = Image.new("RGBA", (8, 6), (10, 20, 30, 255))
        self.assertEqual(MODULE.audit(a, b, self.mask)["changed_protected_pixels"], 24)

    def test_dimension_mismatch_rejected(self):
        Image.new("RGB", (7, 6)).save(self.root/"candidate.png")
        with self.assertRaisesRegex(ValueError, "dimensions"):
            MODULE.run(self.args())

    def test_empty_protection_rejected(self):
        Image.new("L", (8, 6), 0).save(self.root/"mask.png")
        with self.assertRaisesRegex(ValueError, "no fully protected"):
            MODULE.run(self.args())

    def test_no_overwrite(self):
        args = self.args()
        args.output = args.base
        before = MODULE.digest(args.base)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            MODULE.run(args)
        self.assertEqual(MODULE.digest(args.base), before)

    def test_color_profile_mismatch_rejected(self):
        self.candidate.save(self.root/"candidate.png", icc_profile=b"different-profile")
        with self.assertRaisesRegex(ValueError, "ICC profiles differ"):
            MODULE.run(self.args())


if __name__ == "__main__":
    unittest.main()
