# 检验鉴定模块 - D 负责
# 提供 ELA 篡改检测、水印校验、综合鉴定功能

from modules.verification.ela import ela_analysis
from modules.verification.watermark_check import check_watermark
from modules.verification.validator import run_identification

__all__ = [
    "ela_analysis",
    "check_watermark",
    "run_identification",
]
