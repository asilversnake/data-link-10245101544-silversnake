# summer_school_practice_v1.0

这是按实验说明整理的项目目录，适用于 Python 数据分析与实验脚本开发。

## 目录结构

- environment/：环境安装和检查脚本
- student_package/data/：原始数据与样例文件
- student_package/schema/：数据表结构或说明
- student_package/templates/：模板文件
- student_package/src_skeleton/：代码骨架
- student_package/output/：实验输出目录
- student_package/docs/：说明文档

## 一键部署

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File environment\setup.ps1
```

Linux/macOS:

```bash
bash environment/setup.sh
```

## 手动安装与校验

```bash
python -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r environment/requirements.txt
./.venv/bin/python environment/run_student_checks.py
```

在 Windows PowerShell 下，命令等价为：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r environment\requirements.txt
.\.venv\Scripts\python.exe environment\run_student_checks.py
```

## 注意事项

- 后续实验均应在项目根目录中执行。
- 不要直接使用系统 Python 运行实验代码。
- 输出目录与输入目录分开，避免覆盖原始数据。
