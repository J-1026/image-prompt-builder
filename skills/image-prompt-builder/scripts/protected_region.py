"""Audit protected pixels, or composite explicitly selected original regions.

Requires Pillow. White mask pixels are protected; gray pixels are editable
transitions. No resizing, registration, segmentation, or image generation.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_inputs(base_path, candidate_path, mask_path):
    paths = (base_path, candidate_path, mask_path)
    images = []
    for path in paths:
        with Image.open(path) as im:
            im.load()
            if im.getexif().get(274, 1) != 1:
                raise ValueError("EXIF rotation must be resolved explicitly before use")
            images.append(im.copy())
    base, candidate, mask = images
    if base.size != candidate.size or base.size != mask.size:
        raise ValueError("Base, candidate, and mask dimensions must match; no implicit resize")
    if base.mode not in ("RGB", "RGBA") or candidate.mode != base.mode:
        raise ValueError("Base and candidate must use the same RGB or RGBA mode")
    if mask.mode != "L":
        raise ValueError("Protection mask must be an 8-bit grayscale (L) image")
    if mask.histogram()[255] == 0:
        raise ValueError("Protection mask has no fully protected pixels")
    if base.info.get("icc_profile") != candidate.info.get("icc_profile"):
        raise ValueError("ICC profiles differ; resolve color management explicitly")
    return base, candidate, mask


def audit(base, candidate, mask):
    protected = mask.point(lambda value: 255 if value == 255 else 0)
    channels = ImageChops.difference(base, candidate).split()
    maximum = channels[0]
    for channel in channels[1:]:
        maximum = ImageChops.lighter(maximum, channel)
    protected_delta = ImageChops.multiply(maximum, protected)
    histogram = protected_delta.histogram()
    changed = sum(histogram[1:])
    count = mask.histogram()[255]
    return {
        "image_size": list(base.size),
        "protected_pixels": count,
        "changed_protected_pixels": changed,
        "changed_fraction": changed / count,
        "max_channel_delta": max(i for i, n in enumerate(histogram) if n),
        "exact_match": changed == 0,
        "scope": "Only mask=255 pixels; does not assess mask coverage, image goals, or seams",
    }


def run(args):
    base, candidate, mask = load_inputs(args.base, args.candidate, args.mask)
    sources = {key: Path(getattr(args, key)).resolve() for key in ("base", "candidate", "mask")}
    destinations = [Path(p).resolve() for p in (args.output, args.report) if p]
    if len(set(destinations)) != len(destinations):
        raise ValueError("Output and report paths must differ")
    for path in destinations:
        if path in sources.values() or path.exists():
            raise ValueError(f"Refusing to overwrite existing file: {path}")
    report = {
        "operation": args.command,
        "input_sha256": {key: digest(path) for key, path in sources.items()},
        "candidate_audit": audit(base, candidate, mask),
    }
    if args.command == "composite":
        if not args.output or Path(args.output).suffix.lower() != ".png":
            raise ValueError("Composite requires a new --output PNG path")
        output = Image.composite(base, candidate, mask)
        save_options = {}
        if base.info.get("icc_profile"):
            save_options["icc_profile"] = base.info["icc_profile"]
        with open(args.output, "xb") as stream:
            output.save(stream, format="PNG", **save_options)
        with Image.open(args.output) as saved:
            saved.load()
            report["final_audit"] = audit(base, saved, mask)
        report["output_sha256"] = digest(args.output)
        passed = report["final_audit"]["exact_match"]
    else:
        if args.output:
            raise ValueError("Audit mode does not create an image; omit --output")
        passed = report["candidate_audit"]["exact_match"]
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        with open(args.report, "x", encoding="utf-8") as stream:
            stream.write(serialized)
    print(serialized, end="")
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "composite"))
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--mask", required=True)
    parser.add_argument("--output")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        return run(args)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
