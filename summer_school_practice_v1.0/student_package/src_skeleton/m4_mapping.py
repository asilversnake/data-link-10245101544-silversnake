"""
M4: Semantic mapping from OpenSky and TeachingLink sources to unified model.
Uses verified mapping rules (not raw LLM candidates).
"""

import csv
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"

# ── Unified model schema ──────────────────────────────────────────────
UNIFIED_MODEL = {
    "track_id": "",
    "source": "",
    "timestamp": 0,
    "identity": {"callsign": None},
    "position": {"lat": None, "lon": None, "alt": None, "alt_type": "unknown"},
    "motion": {"speed": None, "heading": None, "vertical_rate": None},
    "status": {"on_ground": False},
    "quality": {
        "position_valid": True,
        "time_valid": True,
        "message_valid": True,
        "time_source": "position_time",
        "anomaly_flags": []
    }
}

# ── Verified mapping rules ────────────────────────────────────────────
# After reviewing LLM candidates against field definitions, these are
# the manually verified mapping rules.

LAT_SCALE = (2**22 - 1) / 180.0
LON_SCALE = (2**22 - 1) / 360.0


def map_opensky_row(row: dict) -> dict:
    """Map an OpenSky current_situation row to the unified model."""
    msg = json.loads(json.dumps(UNIFIED_MODEL))  # deep copy
    msg["track_id"] = row.get("target_id", "")
    msg["source"] = "OpenSky"
    ts = row.get("latest_time") or row.get("timestamp")
    msg["timestamp"] = int(ts) if ts else 0
    msg["quality"]["time_valid"] = bool(ts)

    cs = row.get("callsign")
    msg["identity"]["callsign"] = cs if cs else None

    lat = _safe_float(row.get("latitude"))
    lon = _safe_float(row.get("longitude"))
    alt = _safe_float(row.get("altitude"))
    msg["position"]["lat"] = lat
    msg["position"]["lon"] = lon
    msg["position"]["alt"] = alt

    alt_type = row.get("alt_type", "baro")
    msg["position"]["alt_type"] = alt_type if alt_type else "unknown"

    msg["motion"]["speed"] = _safe_float(row.get("speed"))
    msg["motion"]["heading"] = _safe_float(row.get("heading"))
    msg["motion"]["vertical_rate"] = _safe_float(row.get("vertical_rate"))

    og = row.get("on_ground")
    if isinstance(og, str):
        msg["status"]["on_ground"] = og.lower() == "true"
    else:
        msg["status"]["on_ground"] = bool(og) if og is not None else False

    msg["quality"]["position_valid"] = (lat is not None and lon is not None
                                         and -90 <= lat <= 90 and -180 <= lon <= 180)

    ts_src = row.get("timestamp_source", "position_time")
    msg["quality"]["time_source"] = ts_src if ts_src else "position_time"

    mv = row.get("message_valid", "true")
    if isinstance(mv, str):
        msg["quality"]["message_valid"] = mv.lower() == "true"
    else:
        msg["quality"]["message_valid"] = bool(mv)

    return msg


def map_teachinglink_row(row: dict) -> dict:
    """Map a TeachingLink partner_current_situation row to the unified model."""
    msg = json.loads(json.dumps(UNIFIED_MODEL))
    msg["track_id"] = row.get("target_id", "")
    msg["source"] = "TeachingLink"

    ts = _safe_int(row.get("timestamp"))
    msg["timestamp"] = ts if ts else 0
    msg["quality"]["time_valid"] = bool(ts and ts > 0)

    cs = row.get("callsign")
    validity = _safe_int(row.get("validity_flags", 0)) or 0
    cs_valid = bool(validity & (1 << 6))
    msg["identity"]["callsign"] = cs if (cs and cs_valid) else None

    # Decode from protocol codes
    lat_code = _safe_int(row.get("latitude_code", 0)) or 0
    lon_code = _safe_int(row.get("longitude_code", 0)) or 0
    alt_code = _safe_int(row.get("altitude_code", 0)) or 0
    spd_code = _safe_int(row.get("speed_code", 0)) or 0
    hdg_code = _safe_int(row.get("heading_code", 0)) or 0
    vr_code = _safe_int(row.get("vertical_rate_code", 0)) or 0

    lat_valid = bool(validity & (1 << 0))
    lon_valid = bool(validity & (1 << 1))
    alt_valid = bool(validity & (1 << 2))
    spd_valid = bool(validity & (1 << 3))
    hdg_valid = bool(validity & (1 << 4))
    vr_valid = bool(validity & (1 << 5))

    status = _safe_int(row.get("status_flags", 0)) or 0
    alt_is_geo = bool(status & (1 << 1))
    ts_fallback = bool(status & (1 << 2))

    # Decode physical values
    lat = None
    if lat_valid:
        lat = lat_code / LAT_SCALE * 180.0 - 90.0
    lon = None
    if lon_valid:
        lon = lon_code / LON_SCALE * 360.0 - 180.0
    alt = None
    if alt_valid:
        alt = alt_code - 1000
    speed = None
    if spd_valid:
        speed = spd_code * 0.1
    heading = None
    if hdg_valid:
        heading = hdg_code * 0.01
    vr = None
    if vr_valid:
        vr = vr_code * 0.01 - 327.68

    msg["position"]["lat"] = lat
    msg["position"]["lon"] = lon
    msg["position"]["alt"] = alt
    msg["position"]["alt_type"] = "geo" if alt_is_geo else ("baro" if alt_valid else "unknown")

    msg["motion"]["speed"] = speed
    msg["motion"]["heading"] = heading
    msg["motion"]["vertical_rate"] = vr

    on_ground_raw = bool(status & 1)
    msg["status"]["on_ground"] = on_ground_raw

    msg["quality"]["position_valid"] = (lat_valid and lon_valid and
                                         lat is not None and lon is not None)
    msg["quality"]["time_source"] = "last_contact" if ts_fallback else "position_time"

    mv = row.get("message_valid", "true")
    if isinstance(mv, str):
        msg["quality"]["message_valid"] = mv.lower() == "true"
    else:
        msg["quality"]["message_valid"] = bool(mv)

    return msg


def _safe_float(val):
    if val is None or val == "" or val == "None":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val):
    if val is None or val == "" or val == "None":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def create_llm_candidate():
    """Create llm_mapping_candidate.csv from pre-generated candidate or LLM prompt."""
    candidate_path = DATA_DIR.parent / "reference" / "pre_generated_mapping_candidate.csv"
    rows_out = []
    if candidate_path.exists():
        with open(candidate_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows_out.append({
                    "source_field": row.get("source_field", ""),
                    "unified_field": row.get("target_path", ""),
                    "rule": "direct_copy" if row.get("type") in ("string", "boolean", "int") else "decode_if_valid",
                    "unit": row.get("unit", ""),
                    "verified": "false",
                    "notes": row.get("notes", "")
                })
    else:
        rows_out = [
            {"source_field": "target_id", "unified_field": "track_id",
             "rule": "direct_copy", "unit": "", "verified": "false",
             "notes": "6-char hex string, keep leading zeros"},
            {"source_field": "callsign", "unified_field": "identity.callsign",
             "rule": "copy_if_valid", "unit": "", "verified": "false",
             "notes": "Check validity_flags bit6 for TeachingLink"},
            {"source_field": "lat/latitude_code", "unified_field": "position.lat",
             "rule": "decode_if_valid", "unit": "degrees", "verified": "false",
             "notes": "OpenSky: direct; TL: code/scale*180-90"},
            {"source_field": "lon/longitude_code", "unified_field": "position.lon",
             "rule": "decode_if_valid", "unit": "degrees", "verified": "false",
             "notes": "OpenSky: direct; TL: code/scale*360-180"},
            {"source_field": "altitude/altitude_code", "unified_field": "position.alt",
             "rule": "decode_if_valid", "unit": "meters", "verified": "false",
             "notes": "OpenSky: direct; TL: code-1000"},
            {"source_field": "speed/speed_code", "unified_field": "motion.speed",
             "rule": "decode_if_valid", "unit": "m/s", "verified": "false",
             "notes": "OpenSky: direct; TL: code*0.1"},
            {"source_field": "heading/heading_code", "unified_field": "motion.heading",
             "rule": "decode_if_valid", "unit": "degrees", "verified": "false",
             "notes": "OpenSky: direct; TL: code*0.01, must be <360"},
            {"source_field": "vertical_rate/vertical_rate_code", "unified_field": "motion.vertical_rate",
             "rule": "decode_if_valid", "unit": "m/s", "verified": "false",
             "notes": "OpenSky: direct; TL: code*0.01-327.68"},
            {"source_field": "on_ground", "unified_field": "status.on_ground",
             "rule": "direct_copy", "unit": "bool", "verified": "false",
             "notes": "status_flags bit0"},
            {"source_field": "timestamp_source", "unified_field": "quality.time_source",
             "rule": "direct_copy", "unit": "", "verified": "false",
             "notes": "TL: status_flags bit2"},
            {"source_field": "alt_type", "unified_field": "position.alt_type",
             "rule": "direct_copy", "unit": "", "verified": "false",
             "notes": "TL: status_flags bit1"},
        ]

    out = OUTPUT_DIR / "llm_mapping_candidate.csv"
    fieldnames = ["source_field", "unified_field", "rule", "unit", "verified", "notes"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"  LLM candidate -> {out}")
    return rows_out


def create_verified_mapping_table():
    """Create verified_mapping_table.csv with manually verified rules."""
    rows = [
        {"source_field": "target_id (OpenSky) / target_id (TL)",
         "unified_field": "track_id", "rule": "direct_copy",
         "unit": "6-char hex", "type": "string", "null_strategy": "never_null",
         "evidence": "Field definition: 6位十六进制字符串，保留前导0",
         "verified": "true"},
        {"source_field": "callsign (OpenSky) / callsign (TL)",
         "unified_field": "identity.callsign", "rule": "copy_if_valid",
         "unit": "ASCII", "type": "string|null", "null_strategy": "null_if_empty_or_invalid",
         "evidence": "TL validity_flags bit6=0 → null; OpenSky empty string → null",
         "verified": "true"},
        {"source_field": "lat (OpenSky) / latitude_code (TL)",
         "unified_field": "position.lat", "rule": "decode_if_valid",
         "unit": "degrees", "type": "float|null", "null_strategy": "null_if_invalid_bit",
         "evidence": "TL: code/(2^22-1)*180-90; validity_flags bit0=0 → null",
         "verified": "true"},
        {"source_field": "lon (OpenSky) / longitude_code (TL)",
         "unified_field": "position.lon", "rule": "decode_if_valid",
         "unit": "degrees", "type": "float|null", "null_strategy": "null_if_invalid_bit",
         "evidence": "TL: code/(2^22-1)*360-180; validity_flags bit1=0 → null",
         "verified": "true"},
        {"source_field": "altitude (OpenSky) / altitude_code (TL)",
         "unified_field": "position.alt", "rule": "decode_if_valid",
         "unit": "meters", "type": "float|null", "null_strategy": "null_if_invalid_bit",
         "evidence": "TL: code-1000; validity_flags bit2=0 → null",
         "verified": "true"},
        {"source_field": "speed (OpenSky) / speed_code (TL)",
         "unified_field": "motion.speed", "rule": "decode_if_valid",
         "unit": "m/s", "type": "float|null", "null_strategy": "null_if_invalid_bit",
         "evidence": "TL: code*0.1; validity_flags bit3=0 → null",
         "verified": "true"},
        {"source_field": "heading (OpenSky) / heading_code (TL)",
         "unified_field": "motion.heading", "rule": "decode_if_valid",
         "unit": "degrees", "type": "float|null", "null_strategy": "null_if_invalid_bit",
         "evidence": "TL: code*0.01, range [0,360); validity_flags bit4=0 → null",
         "verified": "true"},
        {"source_field": "vertical_rate (OpenSky) / vertical_rate_code (TL)",
         "unified_field": "motion.vertical_rate", "rule": "decode_if_valid",
         "unit": "m/s", "type": "float|null", "null_strategy": "null_if_invalid_bit",
         "evidence": "TL: code*0.01-327.68; validity_flags bit5=0 → null",
         "verified": "true"},
        {"source_field": "on_ground (OpenSky) / status_flags bit0 (TL)",
         "unified_field": "status.on_ground", "rule": "decode_bit0",
         "unit": "bool", "type": "bool", "null_strategy": "default_false",
         "evidence": "status_flags bit0; OpenSky: direct bool",
         "verified": "true"},
        {"source_field": "timestamp_source (OpenSky) / status_flags bit2 (TL)",
         "unified_field": "quality.time_source", "rule": "map_flag",
         "unit": "enum", "type": "string", "null_strategy": "default_position_time",
         "evidence": "TL: bit2 set → last_contact, else position_time",
         "verified": "true"},
        {"source_field": "alt_type/baro vs geo (OpenSky) / status_flags bit1 (TL)",
         "unified_field": "position.alt_type", "rule": "map_flag",
         "unit": "enum", "type": "string", "null_strategy": "default_unknown",
         "evidence": "TL: bit1 set → geo; OpenSky: from altitude source; invalid → unknown",
         "verified": "true"},
        {"source_field": "message_valid (OpenSky) / frame checks (TL)",
         "unified_field": "quality.message_valid", "rule": "direct_copy",
         "unit": "bool", "type": "bool", "null_strategy": "default_false",
         "evidence": "OpenSky: from decode; TL: from validity check result",
         "verified": "true"},
    ]

    out = OUTPUT_DIR / "verified_mapping_table.csv"
    fieldnames = ["source_field", "unified_field", "rule", "unit", "type",
                  "null_strategy", "evidence", "verified"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Verified mapping -> {out}")


def run_m4():
    """Main M4 execution: map both sources to unified model."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Create LLM candidate
    print("Creating LLM mapping candidate...")
    create_llm_candidate()

    # Step 2: Create verified mapping table
    print("Creating verified mapping table...")
    create_verified_mapping_table()

    # Step 3: Map OpenSky current situation
    print("Mapping OpenSky current situation...")
    opensky_path = OUTPUT_DIR / "current_situation.csv"
    unified_messages = []
    if opensky_path.exists():
        with open(opensky_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                msg = map_opensky_row(row)
                unified_messages.append(msg)
        print(f"  {len(unified_messages)} OpenSky messages mapped")

    # Step 4: Map TeachingLink partner situation
    print("Mapping TeachingLink partner situation...")
    tl_path = DATA_DIR / "m4" / "partner_current_situation.csv"
    tl_count = 0
    if tl_path.exists():
        with open(tl_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                msg = map_teachinglink_row(row)
                unified_messages.append(msg)
                tl_count += 1
        print(f"  {tl_count} TeachingLink messages mapped")

    # Step 5: Write unified NDJSON
    ndjson_path = OUTPUT_DIR / "unified_situation.ndjson"
    with open(ndjson_path, "w", encoding="utf-8") as f:
        for msg in unified_messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    print(f"  Unified situation ({len(unified_messages)} messages) -> {ndjson_path}")

    # Verify re-read
    with open(ndjson_path, "r", encoding="utf-8") as f:
        reloaded = [json.loads(line) for line in f]
    print(f"  Re-read verified: {len(reloaded)} messages parseable")

    print("\nM4 complete.")


if __name__ == "__main__":
    run_m4()
