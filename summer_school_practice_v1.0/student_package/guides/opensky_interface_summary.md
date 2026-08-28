# OpenSky Interface Summary

## State Vector Format
The OpenSky Network state vectors are arrays with 17 indexed fields.
Fields at indices 3, 7, 12, 13 may be null.

## Key Fields for Teaching
- index 0: icao24 (string, 6-char hex)
- index 1: callsign (string, up to 8 chars)
- index 3: time_position (int, Unix seconds, nullable)
- index 4: last_contact (int, Unix seconds)
- index 5: longitude (float, degrees)
- index 6: latitude (float, degrees)
- index 7: baro_altitude (float, meters, nullable)
- index 8: on_ground (bool)
- index 9: velocity (float, m/s)
- index 10: true_track (float, degrees)
- index 11: vertical_rate (float, m/s)
- index 13: geo_altitude (float, meters, nullable)
- index 16: position_source (int)

## Data Characteristics
- All timestamps are Unix epoch seconds
- Null indicates missing/unavailable data
- position_source encodes the navigation technology used
