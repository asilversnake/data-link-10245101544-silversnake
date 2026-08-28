"""
M5: Consistency checks — anomaly detection, alert log, quality situation.
Rules: R1 POSITION_MISSING, R2 DATA_DELAYED, R3 DUPLICATE_RECORD, R4 HEADING_OUT_OF_RANGE.
"""

import csv
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"

BATCH_TIME = 1710000120  # Unified batch time


def load_anomaly_rules():
    """Load anomaly rules from CSV."""
    rules_path = DATA_DIR / "m5" / "anomaly_rules.csv"
    rules = {}
    with open(rules_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rules[row["rule_id"]] = row
    return rules


def load_anomaly_cases():
    """Load anomaly test cases from CSV."""
    cases_path = DATA_DIR / "m5" / "anomaly_cases.csv"
    cases = []
    with open(cases_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cases.append(row)
    return cases


def check_position_missing(record: dict, alerts: list):
    """R1: lat or lon is empty/None → POSITION_MISSING (HIGH)."""
    tid = record.get("target_id", "")
    lat = record.get("lat", "").strip() if record.get("lat") is not None else ""
    lon = record.get("lon", "").strip() if record.get("lon") is not None else ""

    missing_fields = []
    if lat == "" or lat == "None":
        missing_fields.append("lat")
    if lon == "" or lon == "None":
        missing_fields.append("lon")

    if missing_fields:
        field_str = ",".join(missing_fields)
        alerts.append({
            "alert_time": BATCH_TIME,
            "target_id": tid,
            "alert_type": "POSITION_MISSING",
            "severity": "HIGH",
            "field": field_str,
            "description": f"Position field(s) {field_str} missing for {tid}"
        })


def check_data_delayed(record: dict, alerts: list):
    """R2: batch_time - record_time > 60s → DATA_DELAYED (MEDIUM)."""
    tid = record.get("target_id", "")
    record_time = _safe_int(record.get("latest_time") or record.get("timestamp"))
    batch_time = _safe_int(record.get("batch_time")) or BATCH_TIME

    if record_time is not None and (batch_time - record_time) > 60:
        delay = batch_time - record_time
        alerts.append({
            "alert_time": batch_time,
            "target_id": tid,
            "alert_type": "DATA_DELAYED",
            "severity": "MEDIUM",
            "field": "timestamp",
            "description": f"Record {tid} delayed by {delay}s (batch={batch_time}, record={record_time})"
        })


def check_duplicate(seen_keys: dict, record: dict, alerts: list):
    """R3: target_id + timestamp already seen → DUPLICATE_RECORD (MEDIUM)."""
    tid = record.get("target_id", "")
    ts = _safe_int(record.get("latest_time") or record.get("timestamp"))
    key = (tid, ts)

    if key in seen_keys:
        alerts.append({
            "alert_time": BATCH_TIME,
            "target_id": tid,
            "alert_type": "DUPLICATE_RECORD",
            "severity": "MEDIUM",
            "field": "target_id,timestamp",
            "description": f"Duplicate record for {tid} at timestamp {ts}"
        })
    else:
        seen_keys[key] = record


def check_heading_out_of_range(record: dict, alerts: list):
    """R4: heading non-empty and (heading < 0 or heading >= 360) → HEADING_OUT_OF_RANGE (MEDIUM)."""
    tid = record.get("target_id", "")
    heading = _safe_float(record.get("heading"))

    if heading is not None and (heading < 0 or heading >= 360):
        alerts.append({
            "alert_time": BATCH_TIME,
            "target_id": tid,
            "alert_type": "HEADING_OUT_OF_RANGE",
            "severity": "MEDIUM",
            "field": "heading",
            "description": f"Heading {heading} out of range [0, 360) for {tid}"
        })


def check_frame_validation(record: dict, alerts: list):
    """Optional: message_valid=false → FRAME_VALIDATION_ERROR."""
    tid = record.get("target_id", "")
    mv = record.get("message_valid", "true")
    if isinstance(mv, str):
        # Only interpret "true"/"false" as boolean; other values are malformed → assume valid
        mv_lower = mv.lower()
        if mv_lower == "false":
            mv = False
        elif mv_lower == "true":
            mv = True
        else:
            # Non-boolean string (e.g. shifted timestamp) → skip frame check
            return
    if not mv:
        alerts.append({
            "alert_time": BATCH_TIME,
            "target_id": tid,
            "alert_type": "FRAME_VALIDATION_ERROR",
            "severity": "HIGH",
            "field": "message_valid",
            "description": f"Frame validation failed for {tid}"
        })


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
        return int(float(val))
    except (ValueError, TypeError):
        return None


def run_m5():
    """Main M5 execution."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load rules and cases
    rules = load_anomaly_rules()
    cases = load_anomaly_cases()
    print(f"Loaded {len(rules)} rules, {len(cases)} test cases")

    alerts = []
    seen_keys = {}

    # Process each case through all mandatory rules
    for record in cases:
        check_position_missing(record, alerts)
        check_data_delayed(record, alerts)
        check_duplicate(seen_keys, record, alerts)
        check_heading_out_of_range(record, alerts)
        check_frame_validation(record, alerts)  # optional

    # Write alert_log.csv
    alert_path = OUTPUT_DIR / "alert_log.csv"
    alert_fields = ["alert_time", "target_id", "alert_type", "severity", "field", "description"]
    with open(alert_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=alert_fields)
        writer.writeheader()
        for alert in alerts:
            writer.writerow(alert)
    print(f"  Alerts: {len(alerts)} -> {alert_path}")

    # Build quality situation
    # Group alerts by target_id
    alert_by_target = defaultdict(list)
    for a in alerts:
        alert_by_target[a["target_id"]].append(a)

    # Build quality_situation from cases
    quality_path = OUTPUT_DIR / "quality_situation.csv"
    quality_fields = [
        "target_id", "timestamp", "position_valid", "delayed", "duplicate_detected",
        "heading_valid", "message_valid", "anomaly_level", "display_status"
    ]

    # Track which targets have which alerts
    target_alerts = defaultdict(lambda: {
        "position_missing": False, "delayed": False,
        "duplicate": False, "heading_oor": False, "frame_error": False
    })
    for a in alerts:
        tid = a["target_id"]
        if a["alert_type"] == "POSITION_MISSING":
            target_alerts[tid]["position_missing"] = True
        elif a["alert_type"] == "DATA_DELAYED":
            target_alerts[tid]["delayed"] = True
        elif a["alert_type"] == "DUPLICATE_RECORD":
            target_alerts[tid]["duplicate"] = True
        elif a["alert_type"] == "HEADING_OUT_OF_RANGE":
            target_alerts[tid]["heading_oor"] = True
        elif a["alert_type"] == "FRAME_VALIDATION_ERROR":
            target_alerts[tid]["frame_error"] = True

    # Use unique target+timestamp combos from cases
    seen_quality = set()
    quality_rows = []
    for record in cases:
        tid = record.get("target_id", "")
        ts = record.get("latest_time") or record.get("timestamp", "")
        key = (tid, str(ts))
        if key in seen_quality:
            continue
        seen_quality.add(key)

        ta = target_alerts[tid]
        position_valid = not ta["position_missing"]
        delayed = ta["delayed"]
        dup = ta["duplicate"]
        heading_valid = not ta["heading_oor"]
        mv = record.get("message_valid", "true")
        if isinstance(mv, str):
            mv_lower = mv.lower()
            if mv_lower == "true":
                mv = True
            elif mv_lower == "false":
                mv = False
            else:
                mv = True  # non-boolean → assume valid
        mv = mv and not ta["frame_error"]

        # Determine anomaly level and display status
        has_high = ta["position_missing"] or ta["frame_error"]
        has_medium = ta["delayed"] or ta["duplicate"] or ta["heading_oor"]

        if has_high:
            anomaly_level = "HIGH"
            display_status = "ERROR"
        elif has_medium:
            anomaly_level = "MEDIUM"
            display_status = "WARNING"
        else:
            anomaly_level = "NONE"
            display_status = "NORMAL"

        quality_rows.append({
            "target_id": tid,
            "timestamp": ts,
            "position_valid": str(position_valid),
            "delayed": str(delayed),
            "duplicate_detected": str(dup),
            "heading_valid": str(heading_valid),
            "message_valid": str(mv),
            "anomaly_level": anomaly_level,
            "display_status": display_status
        })

    with open(quality_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=quality_fields)
        writer.writeheader()
        writer.writerows(quality_rows)
    print(f"  Quality situation: {len(quality_rows)} entries -> {quality_path}")

    # Summary
    high_count = sum(1 for a in alerts if a["severity"] == "HIGH")
    medium_count = sum(1 for a in alerts if a["severity"] == "MEDIUM")
    error_count = sum(1 for r in quality_rows if r["display_status"] == "ERROR")
    warning_count = sum(1 for r in quality_rows if r["display_status"] == "WARNING")
    normal_count = sum(1 for r in quality_rows if r["display_status"] == "NORMAL")
    print(f"  Summary: {high_count} HIGH, {medium_count} MEDIUM alerts")
    print(f"  Display: {error_count} ERROR, {warning_count} WARNING, {normal_count} NORMAL")

    print("\nM5 complete.")


if __name__ == "__main__":
    run_m5()
