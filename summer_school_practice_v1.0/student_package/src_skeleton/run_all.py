"""
M6: Integration pipeline — run M2→M3→M4→M5 from a single entry point.
Clears output directory, runs all stages, verifies each output.
"""

import shutil
import json
import sys
from pathlib import Path

# Add src_skeleton to path
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"

sys.path.insert(0, str(BASE_DIR / "src_skeleton"))


def clear_output():
    """Clear or create output directory."""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("[M6] Output directory cleared.")


def parse_open_source():
    """M2: Parse OpenSky raw states."""
    from m2_protocol import run_m2
    print("\n[M6] === Stage 1: M2 Protocol Parsing ===")
    run_m2()
    _verify(OUTPUT_DIR / "encoded_messages.bin", min_size=41)
    _verify(OUTPUT_DIR / "decoded_partner_states.csv")
    _verify(OUTPUT_DIR / "validation_log.csv")
    _verify(OUTPUT_DIR / "roundtrip_report.csv")


def encode_teaching_messages():
    """Already part of M2."""
    pass


def decode_and_validate_messages():
    """Already part of M2."""
    pass


def persist_records():
    """Optional: already part of M3."""
    pass


def build_tracks_and_situation():
    """M3: Track association and current situation."""
    from m3_tracks import run_m3
    print("\n[M6] === Stage 2: M3 Tracks & Situation ===")
    run_m3()
    _verify(OUTPUT_DIR / "decoded_multitime.csv")
    _verify(OUTPUT_DIR / "track_table.csv")
    _verify(OUTPUT_DIR / "current_situation.csv")


def map_with_verified_rules():
    """M4: Semantic mapping with verified rules."""
    from m4_mapping import run_m4
    print("\n[M6] === Stage 3: M4 Semantic Mapping ===")
    run_m4()
    _verify(OUTPUT_DIR / "llm_mapping_candidate.csv")
    _verify(OUTPUT_DIR / "verified_mapping_table.csv")
    _verify(OUTPUT_DIR / "unified_situation.ndjson")


def consistency_check():
    """M5: Consistency checks and anomaly detection."""
    from m5_quality import run_m5
    print("\n[M6] === Stage 4: M5 Consistency Checks ===")
    run_m5()
    _verify(OUTPUT_DIR / "alert_log.csv")
    _verify(OUTPUT_DIR / "quality_situation.csv")


def export_results():
    """Print summary of all outputs."""
    print("\n[M6] === Output Summary ===")
    required = [
        "encoded_messages.bin", "decoded_partner_states.csv",
        "validation_log.csv", "roundtrip_report.csv",
        "decoded_multitime.csv", "track_table.csv",
        "current_situation.csv", "llm_mapping_candidate.csv",
        "verified_mapping_table.csv", "unified_situation.ndjson",
        "alert_log.csv", "quality_situation.csv"
    ]
    all_ok = True
    for fname in required:
        fpath = OUTPUT_DIR / fname
        if fpath.exists():
            size = fpath.stat().st_size
            print(f"  [OK] {fname} ({size} bytes)")
        else:
            print(f"  [MISSING] {fname}")
            all_ok = False

    # Binary frame count
    bin_path = OUTPUT_DIR / "encoded_messages.bin"
    if bin_path.exists():
        frame_count = bin_path.stat().st_size // 41
        print(f"\n  Frames encoded: {frame_count}")

    # NDJSON message count
    ndjson_path = OUTPUT_DIR / "unified_situation.ndjson"
    if ndjson_path.exists():
        with open(ndjson_path, "r", encoding="utf-8") as f:
            msg_count = sum(1 for _ in f)
        print(f"  Unified messages: {msg_count}")

    if all_ok:
        print("\n[M6] All outputs verified. Pipeline complete.")
    else:
        print("\n[M6] WARNING: Some outputs are missing.")


def _verify(path, min_size=0):
    """Check a file exists and optionally has minimum size."""
    if path.exists():
        size = path.stat().st_size
        if size >= min_size:
            return True
    print(f"  [WARN] {path} missing or too small")
    return False


def main():
    """M6 main pipeline."""
    print("=" * 60)
    print("  M6: Integrated Data-Link Processing Pipeline")
    print("=" * 60)

    clear_output()
    parse_open_source()
    build_tracks_and_situation()
    map_with_verified_rules()
    consistency_check()
    export_results()


if __name__ == "__main__":
    main()
