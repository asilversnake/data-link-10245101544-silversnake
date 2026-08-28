# Source Field Definitions

## OpenSky来源字段
- target_id: 6位十六进制icao24字符串
- callsign: 8字符ASCII呼号（去除尾部空格）
- lat: 纬度，度
- lon: 经度，度
- altitude: 高度，米（优先baro，回退geo）
- alt_type: "baro"或"geo"
- speed: 地速，米/秒
- heading: 航向，度
- vertical_rate: 垂直速度，米/秒
- on_ground: 布尔值
- timestamp_source: "position_time"或"last_contact"
- latest_time: Unix秒
- message_valid: 布尔值

## TeachingLink来源字段
- target_id: 6位小写十六进制
- callsign: ASCII字符串
- latitude_code: 22位整数
- longitude_code: 22位整数
- altitude_code: uint16
- speed_code: uint16
- heading_code: uint16
- vertical_rate_code: uint16
- status_flags: uint8
- validity_flags: uint8
- timestamp: uint32
- message_valid: 布尔值
