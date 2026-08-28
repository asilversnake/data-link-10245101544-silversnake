# M4 AI辅助映射核验说明

## 候选来源

使用 `student_package/reference/pre_generated_mapping_candidate.csv` 作为预生成候选，并结合大模型生成补充字段。候选文件包含13条基本映射规则，覆盖OpenSky来源到统一模型的直接映射。

## 提示词

> 已知两种数据源（OpenSky和TeachingLink）和统一数据模型unified_model.json。
> 请为每种来源的每个字段生成到统一模型的映射规则，包括：
> - 来源字段名称
> - 统一模型路径
> - 转换规则（直接复制/条件映射/解码恢复）
> - 单位
> - 类型
> - 空值策略
> - 依据来源

## 候选结果问题

### 1. 缺少TeachingLink解码规则
预生成候选仅覆盖OpenSky直接映射，未包含TeachingLink协议码到物理值的解码规则（如latitude_code→lat的22位公式恢复）。

### 2. 缺少有效性位检查
候选未说明validity_flags各位对映射的影响。例如callsign需要检查validity_flags bit6，经纬度需要检查bit0/bit1。

### 3. 缺少status_flags解析
候选未包含status_flags中bit0(on_ground)、bit1(alt_type)、bit2(time_source)的位解析规则。

### 4. 空值策略不完整
候选未区分"有效位为0"和"协议整数为0"的语义差异。有效位为0时统一字段应为null；有效位为1且协议码为0时是有效物理零值。

## 修订依据

| 修订项 | 依据 |
|--------|------|
| TeachingLink经纬度解码公式 | teaching_message_spec.md: Q((lat+90)/180×(2^22-1)) |
| 高度解码: code-1000 | teaching_message_spec.md: 偏置1000米 |
| 速度解码: code×0.1 | teaching_message_spec.md: 0.1米/秒分辨率 |
| 航向解码: code×0.01, <360 | teaching_message_spec.md: 0.01度分辨率，0≤heading<360 |
| 垂直速度: code×0.01-327.68 | teaching_message_spec.md: 偏置327.68米/秒 |
| validity_flags位定义 | teaching_message_spec.md 3.4节 |
| status_flags位定义 | teaching_message_spec.md 3.4节 |
| alt_type默认unknown | unified_model.json: 高度无效时为"unknown" |

## 验证结果

使用样例数据验证：
- OpenSky源: a1b2c3 (lat=31.2, lon=121.5, alt=1200) → 正确映射
- TeachingLink源: a1b2c3 (lat_code=2490368) → 2490368/((2^22-1)/180)×180-90 ≈ 31.2 → 正确
- TeachingLink空呼号: validity_flags bit6=0 → callsign=null → 正确
- 真实零值: speed_code=0且有效位=1 → speed=0.0 → 正确

## 适用限制

- 映射规则仅适用于本实验的OpenSky和TeachingLink两种来源
- TeachingLink解码依赖于41字节帧的固定比例因子和偏置
- 不适用于其他航空数据协议（ASTERIX、ADS-B等）
- 统一模型仅包含position、motion、status、quality四类字段
- 新增字段需要重新核验映射规则
