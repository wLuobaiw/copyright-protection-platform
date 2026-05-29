"""
水印嵌入模块 - B 负责实现

接口约定：
    输入: image_path (原图路径), watermark_text (版权信息), output_path (输出路径)
    输出: {"success": bool, "output_path": str, "psnr": float, "message": str}

技术提示：
    - 可使用 LSB（最低有效位）或 DCT/DWT 频域方法
    - LSB 实现简单但抗压缩能力弱
    - DCT/DWT 鲁棒性更好，适合答辩展示
    - PSNR > 40dB 一般认为视觉无损
"""

from PIL import Image
import numpy as np
import os


def embed_watermark(image_path: str, watermark_text: str, output_path: str) -> dict:
    """
    将版权水印嵌入图片。

    TODO: B同学在此实现水印嵌入算法。
    目前为占位实现，仅复制原图到输出路径并返回假数据。
    """
    try:
        img = Image.open(image_path)
        # TODO: 在此实现真正的水印嵌入逻辑
        # 目前仅复制文件作为占位
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path)

        return {
            "success": True,
            "output_path": output_path,
            "psnr": 99.9,   # TODO: 替换为真实PSNR计算
            "message": "占位实现：水印嵌入功能待B同学完成",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
