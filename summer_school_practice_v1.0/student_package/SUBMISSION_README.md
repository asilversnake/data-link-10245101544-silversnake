# 数据链处理链综合运行说明

## 基本信息
- 姓名：silversnake
- 学号：10245101544
- GitHub用户名：silversnake

## 运行环境
- Python版本：3.11.7
- 操作系统：Windows 11
- 依赖库：pandas 2.x, matplotlib 3.7+

## 运行命令
```bash
# 进入项目目录
cd summer_school_practice_v1.0

# 一键部署环境（首次）
powershell -ExecutionPolicy Bypass -File environment\setup.ps1

# 运行综合处理链（清空output目录后重新生成全部成果）
.venv\Scripts\python.exe student_package\src_skeleton\m6_pipeline.py

# 或分模块运行
.venv\Scripts\python.exe student_package\src_skeleton\m2_protocol.py
.venv\Scripts\python.exe student_package\src_skeleton\m3_tracks.py
.venv\Scripts\python.exe student_package\src_skeleton\m4_mapping.py
.venv\Scripts\python.exe student_package\src_skeleton\m5_quality.py
```

## 输入
- `student_package/data/raw_states.json` — 9条OpenSky状态向量
- `student_package/data/partner_messages_multitime.bin` — 9帧多目标多时刻消息（3目标×3时刻）
- `student_package/data/m4/partner_current_situation.csv` — TeachingLink态势数据
- `student_package/data/m5/anomaly_cases.csv` — 10条异常测试用例
- `student_package/data/m5/anomaly_rules.csv` — 4条固定检测规则

## 输出
全部输出位于 `student_package/output/` 目录：

| 文件 | 说明 |
|------|------|
| encoded_messages.bin | 8帧41字节TeachingLink消息 |
| decoded_partner_states.csv | 8条解码接收记录 |
| validation_log.csv | 1条编码错误（heading=360越界） |
| roundtrip_report.csv | 48条往返精度比较 |
| decoded_multitime.csv | 9帧多时刻解码 |
| track_table.csv | 3目标航迹（a1b2c3×3, d4e5f6×3, 998877×3） |
| current_situation.csv | 3目标最新态势 |
| llm_mapping_candidate.csv | 13条大模型映射候选 |
| verified_mapping_table.csv | 12条人工核验映射规则 |
| unified_situation.ndjson | 6条统一模型消息 |
| alert_log.csv | 10条告警（3 HIGH, 7 MEDIUM） |
| quality_situation.csv | 9条质量增强态势 |

## 数据量统计
- 输入记录数：9条（raw_states.json）
- 编码帧数：8帧（1条因heading=360越界被拒绝）
- 有效接收帧数：8帧（全部通过接收校验）
- 航迹目标数：3个（a1b2c3, d4e5f6, 998877）
- 多时刻帧数：9帧（partner_messages_multitime.bin，369字节）
- 统一消息数：6条（OpenSky 3条 + TeachingLink 3条）
- 告警数：11条（4 HIGH + 7 MEDIUM）

## SQLite选做
- 数据库文件：output/states.db
- 写入9条可接受记录，重新读取一致
- 简单查询示例：`SELECT target_id, COUNT(*) FROM decoded_records GROUP BY target_id`

## 映射来源
- LLM候选来源：`student_package/reference/pre_generated_mapping_candidate.csv`（预生成候选）
- 核验方式：依据teaching_message_spec.md和source_field_definitions.md逐项核对语义、单位、类型、空值策略
- 修正内容：补充TeachingLink协议码解码规则、validity_flags位检查、status_flags位解析

## 已知问题与限制
1. heading=360度的记录在编码阶段被拒绝（航向范围[0,360)），不生成对应帧
2. partner_messages_multitime.bin 包含3条合成帧以补全3目标×3时刻的实验要求
3. TeachingLink映射仅覆盖当前态势字段，不包含原始协议帧到物理值的反向映射
4. 一致性检查的FRAME_VALIDATION_ERROR为选做规则，不替代四类必做规则
5. 实验使用离线数据，不涉及实时网络传输或传感器接入
