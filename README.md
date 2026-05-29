# 数字版权保护平台

数据安全与隐私保护课程实践 —— 方向1：版权侵权取证

## 项目简介

为数字创作者提供一站式版权保护方案，涵盖三大核心能力：

| 模块 | 功能 | 对应课程要求 |
|------|------|-------------|
| 作品管理 | 上传原创作品 → 自动嵌入数字水印 → 发布展示 | 信息隐藏 |
| 侵权取证与鉴定 | 上传嫌疑文件 → 填写元信息 → 技术鉴定 → 打包证据压缩包 | 数字取证 + 数据检验 |

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
python run.py

# 浏览器访问
#   作品展示页：    http://localhost:5000/
#   作品管理页：    http://localhost:5000/admin/
#   侵权取证与鉴定：http://localhost:5000/forensics/
```

## 目录结构

```
copyright-protection-platform/
├── run.py                    # 启动入口
├── app.py                    # Flask 应用工厂
├── config.py                 # 全局配置
│
├── modules/                  # 核心算法模块
│   ├── steganography/        # B 负责：水印嵌入/提取
│   ├── forensics/            # C 负责：哈希/元信息/证据打包
│   └── verification/         # D 负责：ELA/水印校验/综合鉴定
│
├── routes/                   # Flask 路由（蓝图）
│   ├── gallery.py            # 页面1：作品展示
│   ├── admin.py              # 页面2：作品管理
│   └── forensics.py          # 页面3：取证与鉴定
│
├── templates/                # Jinja2 页面模板
├── static/                   # CSS / JS / 上传文件
├── data/                     # 运行时数据（不入库）
└── requirements.txt
```

## 模块接口

### 信息隐藏（`modules/steganography/`）

```python
# 嵌入水印
embed_watermark(image_path, watermark_text, output_path) -> dict
# 返回 {"success": bool, "output_path": str, "psnr": float}

# 提取水印
extract_watermark(image_path) -> dict
# 返回 {"success": bool, "watermark": str}
```

### 取证打包（`modules/forensics/`）

```python
# 计算哈希
compute_sha256(file_path) -> str
compute_md5(file_path) -> str

# 生成元信息
create_metadata_json(source_url, capture_time, publisher, notes, officer) -> dict

# 打包证据ZIP
build_evidence_package(suspect_file, metadata, verification_result, audit_log, output_dir) -> dict
# 返回 {"package_path": str, "package_sha256": str, "files": list}
```

### 检验鉴定（`modules/verification/`）

```python
# ELA 篡改检测
ela_analysis(image_path, output_ela_image) -> dict

# 水印校验
check_watermark(image_path, expected_watermark) -> dict

# 综合鉴定（串联所有步骤）
run_identification(suspect_file, expected_watermark) -> dict
# 返回 {"log": [...], "conclusion": {...}}
```

## 证据包结构

```
evidence_YYYYMMDD_HHMMSS.zip
├── suspect.jpg                 # 嫌疑文件
├── metadata.json               # 取证元信息
├── hashes.json                 # 所有文件哈希清单 + 压缩包哈希
├── verification_report.json    # 技术鉴定报告
└── audit_log.json              # 全流程操作审计日志
```

## 协作方式

```bash
# 每人从 main 创建自己的分支
git checkout -b feature/steganography   # B
git checkout -b feature/forensics       # C
git checkout -b feature/verification    # D

# 只修改自己负责的目录
#   B → modules/steganography/
#   C → modules/forensics/
#   D → modules/verification/

# 完成后提交，由组长 review 合并
```

## 技术栈

- **后端**：Python Flask + Jinja2
- **前端**：原生 HTML/CSS/JS
- **图像处理**：Pillow + NumPy + OpenCV
- **存储**：文件系统（`data/` 目录）
