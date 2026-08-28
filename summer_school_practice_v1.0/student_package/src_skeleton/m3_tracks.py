"""
M3: Batch decode multi-time messages, build tracks, generate current situation.
Optional: SQLite persistence and track visualization.
"""

import csv
import json
import sqlite3
import struct
from collections import defaultdict
from pathlib import Path

# Reuse M2 decode function
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from m2_protocol import decode_position_message, MESSAGE_LENGTH

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"


def read_multitime_frames(bin_path: str) -> tuple[list[bytes], list[dict]]:
    """Read binary file, check length, split into 41-byte frames."""
    with open(bin_path, "rb") as f:
        data = f.read()

    total = len(data)
    remainder = total % MESSAGE_LENGTH
    validation_errors = []

    if remainder != 0:
        validation_errors.append({
            "record_no": -1, "target_id": "",
            "stage": "read", "field": "message_length",
            "problem_type": "LENGTH_ERROR",
            "value": str(total),
            "description": f"File length {total} is not a multiple of {MESSAGE_LENGTH}; {remainder} trailing bytes ignored"
        })

    frame_count = total // MESSAGE_LENGTH
    frames = []
    for i in range(frame_count):
        frames.append(data[i * MESSAGE_LENGTH:(i + 1) * MESSAGE_LENGTH])

    return frames, validation_errors


def decode_all_frames(frames: list[bytes]) -> list[dict]:
    """Decode all 41-byte frames and return structured records."""
    decoded = []
    for i, frame in enumerate(frames):
        result = decode_position_message(frame)
        result["frame_index"] = i
        decoded.append(result)
    return decoded


def filter_acceptable(decoded: list[dict]) -> list[dict]:
    """Filter to records where message_valid=True and target_id/timestamp are available."""
    acceptable = []
    for d in decoded:
        if (d.get("message_valid") and
                d.get("target_id") and
                d.get("timestamp") is not None):
            acceptable.append(d)
    return acceptable


def build_tracks(acceptable: list[dict]) -> dict[str, list[dict]]:
    """Group by target_id, sort by timestamp ascending."""
    tracks = defaultdict(list)
    for d in acceptable:
        tracks[d["target_id"]].append(d)
    # Sort each track by timestamp
    for tid in tracks:
        tracks[tid].sort(key=lambda x: x["timestamp"])
    return dict(tracks)


def write_track_table(tracks: dict, output_path: str):
    """Write track_table.csv with track_sequence_no."""
    fieldnames = [
        "target_id", "timestamp", "message_seq", "track_sequence_no",
        "callsign", "latitude", "longitude", "altitude", "speed",
        "heading", "vertical_rate", "on_ground", "altitude_is_geometric",
        "timestamp_fallback", "status_flags", "validity_flags"
    ]
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for tid in sorted(tracks.keys()):
            seq = 0
            for rec in tracks[tid]:
                seq += 1
                writer.writerow({**rec, "track_sequence_no": seq})


def write_current_situation(tracks: dict, output_path: str):
    """Write current_situation.csv: latest record per target."""
    fieldnames = [
        "target_id", "callsign", "latest_time", "latitude", "longitude",
        "altitude", "speed", "heading", "vertical_rate", "on_ground",
        "track_length", "altitude_is_geometric", "timestamp_fallback",
        "status_flags", "validity_flags", "message_valid"
    ]
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for tid in sorted(tracks.keys()):
            latest = tracks[tid][-1]
            writer.writerow({
                **latest,
                "latest_time": latest["timestamp"],
                "track_length": len(tracks[tid])
            })


def write_decoded_multitime(decoded: list[dict], output_path: str):
    """Write decoded_multitime.csv with all decoded records."""
    fieldnames = [
        "frame_index", "target_id", "timestamp", "callsign",
        "latitude", "longitude", "altitude", "speed", "heading",
        "vertical_rate", "on_ground", "altitude_is_geometric",
        "timestamp_fallback", "message_valid",
        "latitude_code", "longitude_code", "altitude_code",
        "speed_code", "heading_code", "vertical_rate_code",
        "status_flags", "validity_flags", "message_seq"
    ]
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for d in decoded:
            writer.writerow(d)


def sqlite_persist(acceptable: list[dict], db_path: str):
    """Optional: Write acceptable records to SQLite and re-read."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS decoded_records")
    c.execute("""
        CREATE TABLE decoded_records (
            target_id TEXT,
            timestamp INTEGER,
            callsign TEXT,
            latitude REAL,
            longitude REAL,
            altitude REAL,
            speed REAL,
            heading REAL,
            vertical_rate REAL,
            on_ground INTEGER,
            altitude_is_geometric INTEGER,
            timestamp_fallback INTEGER,
            message_valid INTEGER,
            message_seq INTEGER
        )
    """)
    for d in acceptable:
        c.execute("""
            INSERT INTO decoded_records VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            d["target_id"], d["timestamp"], d.get("callsign"),
            d.get("latitude"), d.get("longitude"), d.get("altitude"),
            d.get("speed"), d.get("heading"), d.get("vertical_rate"),
            int(d.get("on_ground", False)),
            int(d.get("altitude_is_geometric", False)),
            int(d.get("timestamp_fallback", False)),
            int(d.get("message_valid", False)),
            d.get("message_seq")
        ))
    conn.commit()

    # Re-read and verify
    c.execute("SELECT COUNT(*) FROM decoded_records")
    count = c.fetchone()[0]
    c.execute("SELECT target_id, timestamp FROM decoded_records ORDER BY timestamp LIMIT 3")
    sample = c.fetchall()
    conn.close()
    return count, sample


def create_multitime_bin():
    """Create partner_messages_multitime.bin from M2 valid frames.
    Uses real valid records + synthetic variants to create multi-time tracks.
    """
    from m2_protocol import encode_position_message, validate_record, parse_state_vector

    with open(DATA_DIR / "raw_states.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_states = data["states"]
    records = []
    val_log = []
    for i, item in enumerate(raw_states):
        if isinstance(item, dict):
            vec = item["vector"]
            rid = item["id"]
        else:
            vec = item
            rid = i
        parsed = parse_state_vector(vec)
        validated = validate_record(parsed, rid, val_log)
        if validated:
            records.append((rid, validated))

    frames = []
    seq = 0

    # Encode each valid record as a base frame
    for rid, rec in records:
        frame = encode_position_message(rec, seq)
        frames.append((rid, rec, frame))
        seq += 1

    # Create synthetic time-shifted variants for multi-time tracks
    # For each valid record, create +60s and +120s variants with small position changes
    synthetic_recs = []
    for rid, rec in records:
        for dt, dlat, dlon, dspd in [(60, 0.01, 0.01, 1.0), (120, 0.02, 0.02, 2.0)]:
            syn = dict(rec)
            syn["timestamp"] = rec["timestamp"] + dt
            if syn.get("latitude") is not None:
                syn["latitude"] = syn["latitude"] + dlat
            if syn.get("longitude") is not None:
                syn["longitude"] = syn["longitude"] + dlon
            if syn.get("speed") is not None:
                syn["speed"] = syn["speed"] + dspd
            if syn.get("heading") is not None and syn["heading"] + 0.5 < 360:
                syn["heading"] = syn["heading"] + 0.5
            if syn.get("altitude") is not None:
                syn["altitude"] = syn["altitude"] + 10
            syn["record_no"] = 1000 + rid * 10 + (dt // 60)
            synthetic_recs.append(syn)

    for syn in synthetic_recs:
        frame = encode_position_message(syn, seq)
        frames.append((None, syn, frame))
        seq += 1

    # Write binary
    bin_out = DATA_DIR / "partner_messages_multitime.bin"
    with open(bin_out, "wb") as f:
        for _, _, frame in frames:
            f.write(frame)

    total = len(frames)
    print(f"Created {bin_out}: {total} frames ({total * 41} bytes)")
    return bin_out


def run_m3():
    """Main M3 execution."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Ensure multitime binary exists
    mt_bin = DATA_DIR / "partner_messages_multitime.bin"
    if not mt_bin.exists():
        print("partner_messages_multitime.bin not found, creating from M2 data...")
        mt_bin = create_multitime_bin()

    # Step 1: Read and validate frames
    print(f"Reading {mt_bin}...")
    frames, read_errors = read_multitime_frames(str(mt_bin))
    print(f"  {len(frames)} frames read")

    # Step 2: Decode all frames
    decoded = decode_all_frames(frames)
    valid_count = sum(1 for d in decoded if d.get("message_valid"))
    print(f"  {valid_count} valid, {len(decoded) - valid_count} invalid")

    # Step 3: Write decoded_multitime.csv
    mt_csv = OUTPUT_DIR / "decoded_multitime.csv"
    write_decoded_multitime(decoded, str(mt_csv))
    print(f"  Decoded -> {mt_csv}")

    # Step 4: Filter acceptable records
    acceptable = filter_acceptable(decoded)
    print(f"  {len(acceptable)} acceptable records")

    # Step 5: Build tracks
    tracks = build_tracks(acceptable)
    print(f"  {len(tracks)} tracks: {sorted(tracks.keys())}")

    # Step 6: Write track table
    track_csv = OUTPUT_DIR / "track_table.csv"
    write_track_table(tracks, str(track_csv))
    print(f"  Tracks -> {track_csv}")

    # Step 7: Write current situation
    sit_csv = OUTPUT_DIR / "current_situation.csv"
    write_current_situation(tracks, str(sit_csv))
    print(f"  Situation -> {sit_csv}")

    # Step 8: Optional SQLite
    db_path = OUTPUT_DIR / "states.db"
    count, sample = sqlite_persist(acceptable, str(db_path))
    print(f"  SQLite: {count} records written, sample: {sample}")

    # Write initial and final situation for OpenSky real data section
    _write_receiver_situation(acceptable, tracks)

    print("\nM3 complete.")


def _write_receiver_situation(acceptable, tracks):
    """Write receiver_situation_initial.csv and receiver_situation_final.csv."""
    # Initial: empty
    init_csv = OUTPUT_DIR / "receiver_situation_initial.csv"
    with open(init_csv, "w", encoding="utf-8-sig") as f:
        f.write("target_id,latest_time,latitude,longitude,altitude,speed,heading,vertical_rate,on_ground\n")
    print(f"  Initial situation -> {init_csv}")

    # Final: current situation with simplified headers
    final_csv = OUTPUT_DIR / "receiver_situation_final.csv"
    fieldnames = [
        "target_id", "latest_time", "callsign", "latitude", "longitude",
        "altitude", "speed", "heading", "vertical_rate", "on_ground",
        "track_length", "message_valid"
    ]
    with open(final_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for tid in sorted(tracks.keys()):
            latest = tracks[tid][-1]
            writer.writerow({
                **latest,
                "latest_time": latest["timestamp"],
                "track_length": len(tracks[tid])
            })
    print(f"  Final situation -> {final_csv}")


if __name__ == "__main__":
    run_m3()
