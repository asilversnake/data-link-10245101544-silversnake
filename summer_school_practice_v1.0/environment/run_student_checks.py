from __future__ import annotations

import json
from pathlib import Path


def require_dir(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(f"Missing required directory: {path}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    required_dirs = [
        root / "student_package" / "data",
        root / "student_package" / "schema",
        root / "student_package" / "templates",
        root / "student_package" / "src_skeleton",
        root / "student_package" / "output",
        root / "student_package" / "docs",
    ]

    for d in required_dirs:
        require_dir(d)

    data_dir = root / "student_package" / "data"
    output_dir = root / "student_package" / "output"
    if output_dir.is_relative_to(data_dir):
        raise ValueError("Output directory must be separate from the input data directory.")

    sample_json = data_dir / "sample_data.json"
    sample_csv = data_dir / "sample_data.csv"
    sample_ndjson = data_dir / "sample_data.ndjson"
    sample_bin = data_dir / "sample_data.bin"

    for file in [sample_json, sample_csv, sample_ndjson, sample_bin]:
        if not file.exists():
            raise FileNotFoundError(f"Missing smoke-test sample: {file}")

    with sample_json.open("r", encoding="utf-8") as fh:
        parsed = json.load(fh)
    if not isinstance(parsed, dict):
        raise TypeError("JSON sample should contain a dictionary payload.")

    if sample_csv.stat().st_size == 0:
        raise ValueError("CSV sample should not be empty.")

    lines = sample_ndjson.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("NDJSON sample should not be empty.")
    for line in lines:
        json.loads(line)

    if sample_bin.stat().st_size == 0:
        raise ValueError("Binary sample should not be empty.")

    print("[OK] Environment check passed.")
    print("[OK] Directory structure is valid.")
    print("[OK] Data smoke tests passed for JSON, CSV, NDJSON, and binary samples.")


if __name__ == "__main__":
    main()
