"""
steganography/__init__.py —— 鲁棒水印模块

基于DCT频域的盲水印方案：
- alpha=5.0：确保经uint8量化后DCT系数关系稳定
- 智能嵌入：大图像4象限（抗剪切），小图像全局（容量充足）
- 16bit同步头 + (3,1)重复编码：高容错提取
- 多副本表决：避免假匹配导致的乱码

接口规范：
    embed_watermark(image_path, watermark_text, output_path) -> dict
    extract_watermark(image_path) -> dict
"""

from .embed import embed_watermark
from .extract import extract_watermark

__all__ = ["embed_watermark", "extract_watermark"]