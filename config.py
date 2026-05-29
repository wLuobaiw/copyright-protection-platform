import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 数据存储目录
DATA_DIR = os.path.join(BASE_DIR, "data")
ORIGINALS_DIR = os.path.join(DATA_DIR, "originals")
WATERMARKED_DIR = os.path.join(DATA_DIR, "watermarked")
EVIDENCE_DIR = os.path.join(DATA_DIR, "evidence_packages")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")

# 上传临时目录
UPLOADS_DIR = os.path.join(BASE_DIR, "static", "uploads")

# 作品元数据文件
WORKS_JSON = os.path.join(DATA_DIR, "works.json")

# Flask 配置
SECRET_KEY = "dev-secret-key-change-in-production"
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB 上传限制

# 确保必要目录存在
for _dir in [ORIGINALS_DIR, WATERMARKED_DIR, EVIDENCE_DIR,
             REPORTS_DIR, UPLOADS_DIR]:
    os.makedirs(_dir, exist_ok=True)
