"""
steganography/__init__.py —— 鲁棒水印模块

基于DCT频域的盲水印方案（4象限独立嵌入）：
- alpha=0.5 确保经uint8量化后信号稳定
- 强化QIM：始终保证系数差异 >= alpha*1.5
- 4象限独立循环嵌入：天然抗裁剪
- 多副本表决提取：提高准确率

接口规范：
    embed_watermark(image_path, watermark_text, output_path) -> dict
    extract_watermark(image_path) -> dict
"""

from .embed import embed_watermark
from .extract import extract_watermark

__all__ = ["embed_watermark", "extract_watermark"]