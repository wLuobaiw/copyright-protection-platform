"""
ELA (Error Level Analysis) 误差水平分析 - D 负责实现

原理：
    将图片重新保存为JPEG，计算原始图片与重保存图片的像素差值。
    被篡改过的区域会因为压缩历史不一致而表现出异常误差水平。

接口约定：
    ela_analysis(image_path, output_ela_image)
    -> {"status": str, "anomaly_detected": bool, "detail": str}
"""

from PIL import Image
import numpy as np
import os


def ela_analysis(image_path: str, output_ela_image: str = None) -> dict:
    """
    对图片执行 ELA 篡改检测。

    TODO: D同学在此实现完整的ELA分析。
    目前为占位实现。
    """
    try:
        img = Image.open(image_path)

        # TODO: 实现真正的ELA分析
        # 1. 将原图以质量95重新保存为JPEG
        # 2. 计算原图与重保存图的像素差异
        # 3. 放大差异以便可视化
        # 4. 分析差异图，判断是否存在异常篡改区域

        # 占位：生成一张空白ELA图
        if output_ela_image:
            os.makedirs(os.path.dirname(output_ela_image), exist_ok=True)
            ela_img = Image.new("RGB", (100, 100), "black")
            ela_img.save(output_ela_image)

        return {
            "status": "ok",
            "anomaly_detected": False,
            "detail": "占位实现：ELA分析待D同学完成，默认返回未发现异常",
        }
    except Exception as e:
        return {"status": "error", "anomaly_detected": False, "detail": str(e)}
