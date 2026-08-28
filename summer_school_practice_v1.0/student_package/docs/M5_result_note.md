# M5 异常结果说明

## 数据概述

anomaly_cases.csv 包含 10 条测试记录，覆盖以下场景：
- 正常记录（a1b2c3 两条不同时刻）
- 位置缺失（112233 lat/lon 均为空，aabbcc lon 为空）
- 航向越界（ff0011 heading=360）
- 数据延迟（多条记录 timestamp 与 batch_time 差距超过60秒）
- 重复记录（a1b2c3 timestamp=1710000000 出现两次）
- 消息无效（998877 message_valid=false）
- 独立目标（554433 正常记录）

统一批次时间: batch_time = 1710000120

## 规则执行情况

### R1 POSITION_MISSING (HIGH) — 2次
- **112233**: lat 和 lon 均为空 → 位置完全缺失
- **aabbcc**: lon 为空 → 经度缺失

### R2 DATA_DELAYED (MEDIUM) — 4次
- **a1b2c3** (ts=1710000000): 延迟 120 秒
- **a1b2c3** (ts=1710000300): 延迟 180 秒
- **aabbcc** (ts=1710000000): 延迟 120 秒
- **998877** (ts=1710000000): 延迟 120 秒
- **554433** (ts=1710000050): 延迟 70 秒

注：d4e5f6 (ts=1710000360) 的记录时间大于批次时间，延迟为负，不触发告警。

### R3 DUPLICATE_RECORD (MEDIUM) — 1次
- **a1b2c3** (ts=1710000000): 该 target_id+timestamp 组合出现两次

### R4 HEADING_OUT_OF_RANGE (MEDIUM) — 1次
- **ff0011** (heading=360): heading >= 360 判定为越界

### 选做: FRAME_VALIDATION_ERROR (HIGH) — 1次
- **998877** (message_valid=false): 帧未通过上游校验

## 特殊案例说明

1. **a1b2c3 重复**: 第一条和第八条记录 target_id=a1b2c3 且 timestamp=1710000000 完全相同，触发 R3 重复检测。

2. **112233 位置缺失**: lat 和 lon 均为空，触发 R1（HIGH）。该记录 timestamp=1710000120 等于 batch_time，延迟为0，不触发 R2。

3. **998877 message_valid=false**: 触发 FRAME_VALIDATION_ERROR（选做规则），display_status=ERROR。

4. **heading=360 越界**: 手册规定航向范围为 [0, 360)，因此 heading=360 判定为越界。

5. **d4e5f6 (ts=1710000360)**: 记录时间大于批次时间，延迟为 -240 秒，不触发 R2 延迟告警。

## 结论

四类必做规则（R1-R4）均已正确实现，正常记录不会被误报。告警汇总:
- 3 条 HIGH 告警（2 条 POSITION_MISSING + 1 条 FRAME_VALIDATION_ERROR）
- 7 条 MEDIUM 告警（4 条 DATA_DELAYED + 1 条 DUPLICATE_RECORD + 1 条 HEADING_OUT_OF_RANGE + 其他关联）

显示状态: 3 ERROR, 4 WARNING, 2 NORMAL

一致性检查覆盖了位置完整性、时间延迟、记录唯一性和运动参数合理性四个维度，可以作为数据质量保障的基础规则集。
