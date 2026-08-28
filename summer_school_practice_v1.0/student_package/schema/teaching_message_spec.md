# TeachingLink 教学消息规范 v1.0

## 概述
TeachingLink是自定义教学协议，一帧承载一条位置状态消息。
- 总长度：41字节
- 字节序：网络字节序（大端）
- 数值：无符号整数 + 比例因子 + 偏置，不传输IEEE浮点数

## 帧格式

| 字段 | 偏移 | 类型/长度 | 规则 |
|------|------|-----------|------|
| magic | 0-1 | uint16/2 | 固定0x4453 |
| version | 2 | uint8/1 | 固定1 |
| message_type | 3 | uint8/1 | 固定1（位置状态消息） |
| message_length | 4-5 | uint16/2 | 固定41 |
| message_seq | 6-7 | uint16/2 | 发送序号，65535后模65536回绕 |
| timestamp | 8-11 | uint32/4 | 优先time_position，空时用last_contact |
| target_id | 12-14 | uint24/3 | 6位icao24，必需，保留前导0 |
| callsign | 15-22 | ASCII/8 | 1-8字节有效，不足补0x00 |
| latitude_code | 23-25 | 22位/3 | 最高2位保留为0 |
| longitude_code | 26-28 | 22位/3 | 最高2位保留为0 |
| altitude_code | 29-30 | uint16/2 | 1米分辨率，偏置1000米 |
| speed_code | 31-32 | uint16/2 | 0.1米/秒分辨率 |
| heading_code | 33-34 | uint16/2 | 0.01度分辨率，0<=h<360 |
| vertical_rate_code | 35-36 | uint16/2 | 0.01米/秒，偏置327.68 |
| status_flags | 37 | uint8/1 | bit0:on_ground, bit1:alt_is_geo, bit2:ts_fallback, bit3-7保留为0 |
| validity_flags | 38 | uint8/1 | bit0-6:lat/lon/alt/spd/hdg/vr/callsign有效, bit7保留为0 |
| checksum | 39-40 | uint16/2 | 前39字节之和模65536 |

## 量化规则
Q(y) = floor(y + 0.5)，y为加偏置并除以分辨率后的非负实数。

### 编码公式
| 字段 | 公式 |
|------|------|
| 纬度 | Q((lat+90)/180 × (2^22-1)) |
| 经度 | Q((lon+180)/360 × (2^22-1)) |
| 高度 | Q(altitude_m + 1000) |
| 地速 | Q(speed_m_s / 0.1) |
| 航向 | Q(heading_deg / 0.01) |
| 垂直速度 | Q((vertical_rate + 327.68) / 0.01) |

### 解码公式
| 字段 | 公式 |
|------|------|
| 纬度 | code/(2^22-1)×180 - 90 |
| 经度 | code/(2^22-1)×360 - 180 |
| 高度 | code - 1000 |
| 地速 | code × 0.1 |
| 航向 | code × 0.01 |
| 垂直速度 | code × 0.01 - 327.68 |

## 接收判据
1. 长度必须为41字节，message_length必须为41
2. magic=0x4453, version=1, message_type=1
3. checksum匹配前39字节之和模65536
4. 经纬度3字节最高2位为0，两个标志字节保留位为0
5. 有效位与占位字节一致
6. target_id、timestamp、on_ground必需可用
7. 可选字段缺失不使整帧无效
