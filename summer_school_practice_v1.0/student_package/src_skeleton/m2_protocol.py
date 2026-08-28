"""
M2: Protocol parsing and message codec for TeachingLink 41-byte frames.
"""

import struct
import json
import csv
import os
from pathlib import Path


# ── Constants ──────────────────────────────────────────────────────────────
MAGIC = 0x4453
VERSION = 1
MESSAGE_TYPE = 1
MESSAGE_LENGTH = 41

LAT_SCALE = (2**22 - 1) / 180.0
LON_SCALE = (2**22 - 1) / 360.0
LAT_MAX = 2**22 - 1
LON_MAX = 2**22 - 1

ALT_OFFSET = 1000
ALT_RES = 1.0
SPD_RES = 0.1
HDG_RES = 0.01
VR_OFFSET = 327.68
VR_RES = 0.01

FIELD_NAMES = [
    "icao24", "callsign", "origin_country", "time_position", "last_contact",
    "longitude", "latitude", "baro_altitude", "on_ground", "velocity",
    "true_track", "vertical_rate", "unknown12", "geo_altitude",
    "unknown14", "unknown15", "position_source"
]

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"


def quantize(value):
    """Q(y) = floor(y + 0.5)"""
    return int(value + 0.5)


def calculate_checksum(data_without_checksum: bytes) -> int:
    """Sum of first 39 bytes modulo 65536."""
    return sum(data_without_checksum) % 65536


def parse_state_vector(vector: list) -> dict:
    """Parse an OpenSky state vector into a named dict."""
    record = {}
    for i, name in enumerate(FIELD_NAMES):
        if i < len(vector):
            record[name] = vector[i]
        else:
            record[name] = None
    return record


def validate_record(record: dict, record_no: int, validation_log: list):
    """Validate a parsed record and return a sender internal state dict."""
    errors = []
    target_id = record.get("icao24")
    if not target_id or not isinstance(target_id, str) or len(target_id) != 6:
        validation_log.append({
            "record_no": record_no, "target_id": str(target_id),
            "stage": "parse", "field": "icao24",
            "problem_type": "REQUIRED_FIELD_MISSING",
            "value": str(target_id),
            "description": "icao24 must be exactly 6 hex characters"
        })
        return None

    # callsign: strip, check ASCII and length
    raw_callsign = record.get("callsign", "")
    if raw_callsign is None:
        callsign = ""
    else:
        callsign = raw_callsign.strip()

    if len(callsign) > 0:
        if len(callsign) > 8:
            validation_log.append({
                "record_no": record_no, "target_id": target_id,
                "stage": "parse", "field": "callsign",
                "problem_type": "LENGTH_ERROR",
                "value": callsign,
                "description": f"callsign length {len(callsign)} > 8"
            })
            return None
        try:
            callsign.encode("ascii")
        except UnicodeEncodeError:
            validation_log.append({
                "record_no": record_no, "target_id": target_id,
                "stage": "parse", "field": "callsign",
                "problem_type": "ENCODING_ERROR",
                "value": callsign,
                "description": "callsign contains non-ASCII characters"
            })
            return None

    # timestamp: prefer time_position, fallback to last_contact
    ts = record.get("time_position")
    ts_source = "position_time"
    if ts is None:
        ts = record.get("last_contact")
        ts_source = "last_contact"
        if ts is None:
            validation_log.append({
                "record_no": record_no, "target_id": target_id,
                "stage": "parse", "field": "timestamp",
                "problem_type": "MISSING",
                "value": "None",
                "description": "Both time_position and last_contact are null"
            })
            return None

    # on_ground: required
    on_ground = record.get("on_ground")
    if on_ground is None or not isinstance(on_ground, bool):
        validation_log.append({
            "record_no": record_no, "target_id": target_id,
            "stage": "parse", "field": "on_ground",
            "problem_type": "REQUIRED_FIELD_MISSING",
            "value": str(on_ground),
            "description": "on_ground must be a boolean"
        })
        return None

    # altitude: prefer baro, fallback geo
    altitude = record.get("baro_altitude")
    alt_type = "baro"
    altitude_is_geometric = False
    if altitude is None:
        altitude = record.get("geo_altitude")
        alt_type = "geo"
        altitude_is_geometric = True

    # heading: check range [0, 360)
    heading = record.get("true_track")
    if heading is not None and (heading < 0 or heading >= 360):
        validation_log.append({
            "record_no": record_no, "target_id": target_id,
            "stage": "parse", "field": "true_track",
            "problem_type": "OUT_OF_RANGE",
            "value": str(heading),
            "description": f"heading {heading} out of range [0, 360)"
        })
        return None

    return {
        "target_id": target_id,
        "callsign": callsign if callsign else None,
        "timestamp": int(ts),
        "timestamp_source": ts_source,
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "altitude": altitude,
        "alt_type": alt_type,
        "altitude_is_geometric": altitude_is_geometric,
        "speed": record.get("velocity"),
        "heading": record.get("true_track"),
        "vertical_rate": record.get("vertical_rate"),
        "on_ground": on_ground,
        "record_no": record_no,
    }


def encode_position_message(record: dict, message_seq: int) -> bytes:
    """Encode a sender internal record into a 41-byte TeachingLink frame."""
    frame = bytearray(MESSAGE_LENGTH)

    # Header
    struct.pack_into("!HBBHH", frame, 0, MAGIC, VERSION, MESSAGE_TYPE, MESSAGE_LENGTH, message_seq & 0xFFFF)

    # Timestamp (uint32)
    struct.pack_into("!I", frame, 8, record["timestamp"] & 0xFFFFFFFF)

    # target_id (uint24) — 3 bytes big-endian
    tid = int(record["target_id"], 16)
    frame[12] = (tid >> 16) & 0xFF
    frame[13] = (tid >> 8) & 0xFF
    frame[14] = tid & 0xFF

    # callsign (8 bytes ASCII, zero-padded)
    cs = record.get("callsign")
    cs_bytes = cs.encode("ascii") if cs else b""
    cs_padded = cs_bytes.ljust(8, b"\x00")[:8]
    frame[15:23] = cs_padded

    # validity_flags build
    validity = 0
    lat_valid = record.get("latitude") is not None
    lon_valid = record.get("longitude") is not None
    alt_valid = record.get("altitude") is not None
    spd_valid = record.get("speed") is not None
    hdg_valid = record.get("heading") is not None
    vr_valid = record.get("vertical_rate") is not None
    cs_valid = record.get("callsign") is not None

    if lat_valid:
        validity |= (1 << 0)
    if lon_valid:
        validity |= (1 << 1)
    if alt_valid:
        validity |= (1 << 2)
    if spd_valid:
        validity |= (1 << 3)
    if hdg_valid:
        validity |= (1 << 4)
    if vr_valid:
        validity |= (1 << 5)
    if cs_valid:
        validity |= (1 << 6)

    # status_flags build
    status = 0
    if record.get("on_ground"):
        status |= (1 << 0)
    if record.get("altitude_is_geometric"):
        status |= (1 << 1)
    if record.get("timestamp_source") == "last_contact":
        status |= (1 << 2)

    # Encode latitude (22-bit)
    lat_code = 0
    if lat_valid:
        lat_val = record["latitude"]
        if lat_val < -90 or lat_val > 90:
            raise ValueError(f"Latitude {lat_val} out of range [-90, 90]")
        lat_code = quantize((lat_val + 90) / 180.0 * LAT_MAX)
        lat_code = min(lat_code, LAT_MAX)
    # Pack into 3 bytes (22 bits, top 2 bits = 0)
    struct.pack_into("!I", frame, 23, lat_code)

    # Encode longitude (22-bit)
    lon_code = 0
    if lon_valid:
        lon_val = record["longitude"]
        if lon_val < -180 or lon_val > 180:
            raise ValueError(f"Longitude {lon_val} out of range [-180, 180]")
        lon_code = quantize((lon_val + 180) / 360.0 * LON_MAX)
        lon_code = min(lon_code, LON_MAX)
    struct.pack_into("!I", frame, 26, lon_code)

    # Encode altitude (uint16, offset 1000m)
    alt_code = 0
    if alt_valid:
        alt_code = quantize(record["altitude"] + ALT_OFFSET)
    struct.pack_into("!H", frame, 29, alt_code & 0xFFFF)

    # Encode speed (uint16, 0.1 m/s)
    spd_code = 0
    if spd_valid:
        spd_code = quantize(record["speed"] / SPD_RES)
    struct.pack_into("!H", frame, 31, spd_code & 0xFFFF)

    # Encode heading (uint16, 0.01 degree)
    hdg_code = 0
    if hdg_valid:
        hdg_val = record["heading"]
        if hdg_val < 0 or hdg_val >= 360:
            raise ValueError(f"Heading {hdg_val} out of range [0, 360)")
        hdg_code = quantize(hdg_val / HDG_RES)
    struct.pack_into("!H", frame, 33, hdg_code & 0xFFFF)

    # Encode vertical rate (uint16, offset 327.68, res 0.01)
    vr_code = 0
    if vr_valid:
        vr_code = quantize((record["vertical_rate"] + VR_OFFSET) / VR_RES)
    struct.pack_into("!H", frame, 35, vr_code & 0xFFFF)

    # Flags
    frame[37] = status & 0xFF
    frame[38] = validity & 0xFF

    # Checksum
    cksum = calculate_checksum(bytes(frame[:39]))
    struct.pack_into("!H", frame, 39, cksum)

    return bytes(frame)


def decode_position_message(data: bytes) -> dict:
    """Decode a 41-byte TeachingLink frame into a structured dict."""
    result = {"raw_data": data.hex(), "message_valid": False, "errors": []}

    # Length check
    if len(data) != MESSAGE_LENGTH:
        result["errors"].append({
            "stage": "decode", "field": "message_length",
            "problem_type": "LENGTH_ERROR",
            "value": str(len(data)),
            "description": f"Frame length {len(data)} != {MESSAGE_LENGTH}"
        })
        return result

    # Header fields
    magic, version, msg_type, msg_len, msg_seq = struct.unpack_from("!HBBHH", data, 0)

    if magic != MAGIC:
        result["errors"].append({
            "stage": "decode", "field": "magic",
            "problem_type": "MAGIC_ERROR",
            "value": hex(magic),
            "description": f"Magic {hex(magic)} != {hex(MAGIC)}"
        })
        return result

    if version != VERSION:
        result["errors"].append({
            "stage": "decode", "field": "version",
            "problem_type": "VERSION_ERROR",
            "value": str(version),
            "description": f"Version {version} != {VERSION}"
        })
        return result

    if msg_type != MESSAGE_TYPE:
        result["errors"].append({
            "stage": "decode", "field": "message_type",
            "problem_type": "MESSAGE_TYPE_ERROR",
            "value": str(msg_type),
            "description": f"Message type {msg_type} != {MESSAGE_TYPE}"
        })
        return result

    if msg_len != MESSAGE_LENGTH:
        result["errors"].append({
            "stage": "decode", "field": "message_length",
            "problem_type": "LENGTH_ERROR",
            "value": str(msg_len),
            "description": f"message_length {msg_len} != {MESSAGE_LENGTH}"
        })
        return result

    # Checksum
    expected_cksum = calculate_checksum(data[:39])
    actual_cksum = struct.unpack_from("!H", data, 39)[0]
    if expected_cksum != actual_cksum:
        result["errors"].append({
            "stage": "decode", "field": "checksum",
            "problem_type": "CHECKSUM_ERROR",
            "value": hex(actual_cksum),
            "description": f"Checksum {hex(actual_cksum)} != expected {hex(expected_cksum)}"
        })
        return result

    # Timestamp
    timestamp = struct.unpack_from("!I", data, 8)[0]

    # target_id (uint24) — read 3 bytes big-endian
    tid_raw = (data[12] << 16) | (data[13] << 8) | data[14]
    target_id = format(tid_raw, "06x")

    # callsign
    cs_bytes = data[15:23]
    cs = cs_bytes.rstrip(b"\x00").decode("ascii", errors="replace")

    # latitude_code (22 bits from 3 bytes)
    lat_raw = struct.unpack_from("!I", data, 23)[0] & 0x003FFFFF  # mask to 22 bits
    # Check reserved bits
    lat_full = struct.unpack_from("!I", data, 23)[0]
    if (lat_full >> 22) != 0:
        result["errors"].append({
            "stage": "decode", "field": "latitude_code",
            "problem_type": "RESERVED_BITS_ERROR",
            "value": hex(lat_full),
            "description": "Latitude code has non-zero reserved bits"
        })

    # longitude_code (22 bits from 3 bytes)
    lon_raw = struct.unpack_from("!I", data, 26)[0] & 0x003FFFFF
    lon_full = struct.unpack_from("!I", data, 26)[0]
    if (lon_full >> 22) != 0:
        result["errors"].append({
            "stage": "decode", "field": "longitude_code",
            "problem_type": "RESERVED_BITS_ERROR",
            "value": hex(lon_full),
            "description": "Longitude code has non-zero reserved bits"
        })

    altitude_code = struct.unpack_from("!H", data, 29)[0]
    speed_code = struct.unpack_from("!H", data, 31)[0]
    heading_code = struct.unpack_from("!H", data, 33)[0]
    vr_code = struct.unpack_from("!H", data, 35)[0]

    status_flags = data[37]
    validity_flags = data[38]

    # Check reserved bits in flags
    if (status_flags & 0xF8) != 0:  # bits 3-7
        result["errors"].append({
            "stage": "decode", "field": "status_flags",
            "problem_type": "RESERVED_BITS_ERROR",
            "value": bin(status_flags),
            "description": "status_flags bits 3-7 must be 0"
        })
    if (validity_flags & 0x80) != 0:  # bit 7
        result["errors"].append({
            "stage": "decode", "field": "validity_flags",
            "problem_type": "RESERVED_BITS_ERROR",
            "value": bin(validity_flags),
            "description": "validity_flags bit 7 must be 0"
        })

    # Check FLAG_VALUE_INCONSISTENCY
    lat_valid = bool(validity_flags & (1 << 0))
    lon_valid = bool(validity_flags & (1 << 1))
    alt_valid = bool(validity_flags & (1 << 2))
    spd_valid = bool(validity_flags & (1 << 3))
    hdg_valid = bool(validity_flags & (1 << 4))
    vr_valid = bool(validity_flags & (1 << 5))
    cs_valid = bool(validity_flags & (1 << 6))

    # If valid bit is 0 but placeholder is non-zero, flag inconsistency
    if not lat_valid and lat_raw != 0:
        result["errors"].append({
            "stage": "decode", "field": "latitude_code",
            "problem_type": "FLAG_VALUE_INCONSISTENCY",
            "value": str(lat_raw),
            "description": "Latitude valid bit=0 but code is non-zero"
        })
    if not lon_valid and lon_raw != 0:
        result["errors"].append({
            "stage": "decode", "field": "longitude_code",
            "problem_type": "FLAG_VALUE_INCONSISTENCY",
            "value": str(lon_raw),
            "description": "Longitude valid bit=0 but code is non-zero"
        })
    if not alt_valid and altitude_code != 0:
        result["errors"].append({
            "stage": "decode", "field": "altitude_code",
            "problem_type": "FLAG_VALUE_INCONSISTENCY",
            "value": str(altitude_code),
            "description": "Altitude valid bit=0 but code is non-zero"
        })
    if not spd_valid and speed_code != 0:
        result["errors"].append({
            "stage": "decode", "field": "speed_code",
            "problem_type": "FLAG_VALUE_INCONSISTENCY",
            "value": str(speed_code),
            "description": "Speed valid bit=0 but code is non-zero"
        })
    if not hdg_valid and heading_code != 0:
        result["errors"].append({
            "stage": "decode", "field": "heading_code",
            "problem_type": "FLAG_VALUE_INCONSISTENCY",
            "value": str(heading_code),
            "description": "Heading valid bit=0 but code is non-zero"
        })
    if not vr_valid and vr_code != 0:
        result["errors"].append({
            "stage": "decode", "field": "vertical_rate_code",
            "problem_type": "FLAG_VALUE_INCONSISTENCY",
            "value": str(vr_code),
            "description": "VR valid bit=0 but code is non-zero"
        })
    if not cs_valid and cs != "":
        result["errors"].append({
            "stage": "decode", "field": "callsign",
            "problem_type": "FLAG_VALUE_INCONSISTENCY",
            "value": cs,
            "description": "Callsign valid bit=0 but callsign is non-empty"
        })

    # Decode physical values (only if valid bit is set)
    lat = None
    if lat_valid:
        lat = lat_raw / LAT_MAX * 180.0 - 90.0

    lon = None
    if lon_valid:
        lon = lon_raw / LON_MAX * 360.0 - 180.0

    alt = None
    if alt_valid:
        alt = altitude_code - ALT_OFFSET

    speed = None
    if spd_valid:
        speed = speed_code * SPD_RES

    heading = None
    if hdg_valid:
        heading = heading_code * HDG_RES

    vr = None
    if vr_valid:
        vr = vr_code * VR_RES - VR_OFFSET

    on_ground = bool(status_flags & 1)
    alt_is_geo = bool(status_flags & 2)
    ts_fallback = bool(status_flags & 4)

    result.update({
        "message_valid": len(result["errors"]) == 0,
        "target_id": target_id,
        "timestamp": timestamp,
        "callsign": cs if cs else None,
        "latitude": lat,
        "longitude": lon,
        "altitude": alt,
        "speed": speed,
        "heading": heading,
        "vertical_rate": vr,
        "on_ground": on_ground,
        "altitude_is_geometric": alt_is_geo,
        "timestamp_fallback": ts_fallback,
        "latitude_code": lat_raw,
        "longitude_code": lon_raw,
        "altitude_code": altitude_code,
        "speed_code": speed_code,
        "heading_code": heading_code,
        "vertical_rate_code": vr_code,
        "status_flags": status_flags,
        "validity_flags": validity_flags,
        "message_seq": msg_seq,
    })

    return result


def run_m2():
    """Main M2 execution: parse, encode, decode, validate, roundtrip."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load input data
    with open(DATA_DIR / "raw_states.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_states = data["states"]
    validation_log = []
    internal_records = []
    encoded_frames = []
    decoded_records = []
    roundtrip_data = []

    # ── Step 1: Parse and validate ──
    for i, item in enumerate(raw_states):
        # Support both {"id": N, "vector": [...]} and direct array [...]
        if isinstance(item, dict):
            vec = item["vector"]
            record_no = item["id"]
        else:
            vec = item
            record_no = i
        parsed = parse_state_vector(vec)
        validated = validate_record(parsed, record_no, validation_log)
        if validated:
            internal_records.append(validated)

    # ── Step 2: Encode ──
    for i, rec in enumerate(internal_records):
        try:
            frame = encode_position_message(rec, i)
            encoded_frames.append((rec, frame))
        except (ValueError, struct.error) as e:
            validation_log.append({
                "record_no": rec["record_no"],
                "target_id": rec["target_id"],
                "stage": "encode", "field": "",
                "problem_type": "OUT_OF_RANGE",
                "value": str(e),
                "description": f"Encode error: {e}"
            })

    # ── Write encoded_messages.bin ──
    bin_path = OUTPUT_DIR / "encoded_messages.bin"
    with open(bin_path, "wb") as f:
        for _, frame in encoded_frames:
            f.write(frame)

    # ── Step 3: Decode ──
    for rec, frame in encoded_frames:
        decoded = decode_position_message(frame)
        decoded["original_record_no"] = rec["record_no"]

        # Build roundtrip comparison
        for field in ["latitude", "longitude", "altitude", "speed", "heading", "vertical_rate"]:
            source_val = rec.get(field)
            is_valid = source_val is not None
            code_key = field + "_code" if field != "altitude" else "altitude_code"
            proto_code = decoded.get(code_key, 0)
            decoded_val = decoded.get(field)
            error = abs(source_val - decoded_val) if (source_val is not None and decoded_val is not None) else None
            tolerance = 1.0  # one quantization unit
            passed = (error is not None and error <= tolerance) if (source_val is not None) else True

            roundtrip_data.append({
                "target_id": rec["target_id"],
                "field_name": field,
                "source_value": source_val if source_val is not None else "None",
                "is_valid": is_valid,
                "protocol_code": proto_code,
                "decoded_value": decoded_val if decoded_val is not None else "None",
                "error": f"{error:.6f}" if error is not None else "N/A",
                "tolerance": tolerance,
                "passed": "True" if passed else "False",
            })

        decoded_records.append(decoded)

    # ── Write decoded_partner_states.csv ──
    csv_path = OUTPUT_DIR / "decoded_partner_states.csv"
    fieldnames = [
        "target_id", "callsign", "timestamp", "latitude", "longitude",
        "altitude", "speed", "heading", "vertical_rate", "on_ground",
        "altitude_is_geometric", "timestamp_fallback", "message_valid",
        "latitude_code", "longitude_code", "altitude_code", "speed_code",
        "heading_code", "vertical_rate_code", "status_flags", "validity_flags",
        "message_seq"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for d in decoded_records:
            writer.writerow(d)

    # ── Write validation_log.csv ──
    log_path = OUTPUT_DIR / "validation_log.csv"
    log_fields = ["record_no", "target_id", "stage", "field", "problem_type", "value", "description"]
    with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=log_fields)
        writer.writeheader()
        for entry in validation_log:
            writer.writerow(entry)

    # ── Write roundtrip_report.csv ──
    rt_path = OUTPUT_DIR / "roundtrip_report.csv"
    rt_fields = [
        "target_id", "field_name", "source_value", "is_valid",
        "protocol_code", "decoded_value", "error", "tolerance", "passed"
    ]
    with open(rt_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rt_fields)
        writer.writeheader()
        for entry in roundtrip_data:
            writer.writerow(entry)

    print(f"M2 complete:")
    print(f"  Parsed {len(raw_states)} records, {len(internal_records)} valid")
    print(f"  Encoded {len(encoded_frames)} frames -> {bin_path}")
    print(f"  Decoded {len(decoded_records)} records -> {csv_path}")
    print(f"  Validation errors: {len(validation_log)} -> {log_path}")
    print(f"  Roundtrip entries: {len(roundtrip_data)} -> {rt_path}")


if __name__ == "__main__":
    run_m2()
