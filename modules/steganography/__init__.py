"""
steganography/__init__.py —— 鲁棒水印模块

基于DCT频域的盲水印方案，具备以下特性：
- 4象限独立循环嵌入：每个象限包含完整水印副本，天然抗裁剪
- 中频QIM调制：抵抗JPEG压缩、高斯/椒盐噪声、亮度/对比度调整
- 16bit同步头 + (3,1)重复编码：高容错提取
- 多副本表决：综合多个象限结果，提高提取准确率

接口规范（与README一致）：
    embed_watermark(image_path, watermark_text, output_path) -> dict
    extract_watermark(image_path) -> dict
"""

from .embed import embed_watermark
from .extract import extract_watermark

__all__ = ["embed_watermark", "extract_watermark"]