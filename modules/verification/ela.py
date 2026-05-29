"""
ELA (Error Level Analysis) 误差水平分析 - D 负责实现

原理：
    将图片以固定质量重新保存为JPEG，计算原始图片与重保存图片的像素差值。
    被篡改过的区域会因为压缩历史不一致而表现出异常误差水平。

接口约定：
    ela_analysis(image_path, output_ela_image)
    -> {"status": str, "anomaly_detected": bool, "detail": str}
"""

from PIL import Image
import numpy as np
import os
import tempfile


# ELA 分析参数
ELA_QUALITY = 90          # 重保存 JPEG 质量
ELA_SCALE_FACTOR = 15     # 差异放大倍数（提高对比度）
ANOMALY_THRESHOLD = 25    # 异常像素亮度阈值（0-255），超过此值视为异常区域
ANOMALY_RATIO_THRESHOLD = 0.05  # 异常像素占比阈值，超过此比例判定为疑似篡改


def ela_analysis(image_path: str, output_ela_image: str = None) -> dict:
    """
    对图片执行 ELA 篡改检测。

    流程：
        1. 读取原图并转为 RGB 模式
        2. 以指定质量将原图重新保存为 JPEG（临时文件）
        3. 重新读入该 JPEG，计算与原图的像素级差异
        4. 放大差异值以便可视化
        5. 根据异常像素占比判断是否存在篡改区域

    Args:
        image_path: 待检测图片路径
        output_ela_image: 可选，ELA 结果图输出路径（PNG格式）

    Returns:
        dict: {"status": str, "anomaly_detected": bool, "detail": str,
               "anomaly_ratio": float, "ela_image_path": str|None}
    """
    tmp_path = None
    try:
        original = Image.open(image_path).convert("RGB")
        original_array = np.array(original, dtype=np.float32)

        # 步骤1：将原图以固定质量重新保存为 JPEG
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(tmp_fd)
        original.save(tmp_path, "JPEG", quality=ELA_QUALITY)

        # 步骤2：读回重压缩后的图片
        recompressed = Image.open(tmp_path).convert("RGB")
        recompressed_array = np.array(recompressed, dtype=np.float32)

        # 步骤3：计算像素级绝对差异（逐通道最大差异）
        diff_array = np.abs(original_array - recompressed_array)
        # 取 RGB 三通道中的最大值作为该像素的误差
        diff_max = np.max(diff_array, axis=2)

        # 步骤4：放大差异以增强可视化
        ela_array = np.clip(diff_max * ELA_SCALE_FACTOR, 0, 255).astype(np.uint8)

        # 步骤5：分析异常区域
        anomaly_mask = ela_array > ANOMALY_THRESHOLD
        anomaly_pixel_count = np.sum(anomaly_mask)
        total_pixel_count = ela_array.size
        anomaly_ratio = float(anomaly_pixel_count) / total_pixel_count if total_pixel_count > 0 else 0.0

        anomaly_detected = anomaly_ratio > ANOMALY_RATIO_THRESHOLD

        # 生成 ELA 结果图（伪彩色热力图）
        if output_ela_image:
            os.makedirs(os.path.dirname(output_ela_image) or ".", exist_ok=True)
            ela_img = Image.fromarray(ela_array, mode="L")
            # 应用色彩映射，使异常区域更明显（使用 PIL 的调色板模式模拟热力图）
            ela_colored = _apply_heatmap(ela_img)
            ela_colored.save(output_ela_image, "PNG")

        # 根据分析结果生成详情信息
        if anomaly_detected:
            detail = (
                f"ELA检测发现异常：异常像素占比 {anomaly_ratio:.2%}（阈值 {ANOMALY_RATIO_THRESHOLD:.2%}），"
                f"图片可能存在篡改或合成痕迹。异常区域误差水平显著高于正常区域，"
                f"建议结合元数据分析与视觉审查进一步确认。"
            )
        else:
            detail = (
                f"ELA检测未发现明显异常：异常像素占比 {anomaly_ratio:.2%}（阈值 {ANOMALY_RATIO_THRESHOLD:.2%}），"
                f"图片各区域压缩误差水平均匀，未检测到典型篡改特征。"
            )

        return {
            "status": "ok",
            "anomaly_detected": anomaly_detected,
            "detail": detail,
            "anomaly_ratio": round(anomaly_ratio, 6),
            "ela_image_path": output_ela_image,
        }

    except FileNotFoundError:
        return {"status": "error", "anomaly_detected": False,
                "detail": f"文件未找到: {image_path}"}
    except Exception as e:
        return {"status": "error", "anomaly_detected": False,
                "detail": f"ELA分析异常: {str(e)}"}
    finally:
        # 清理临时 JPEG 文件
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _apply_heatmap(gray_image: Image.Image) -> Image.Image:
    """
    对灰度 ELA 图应用伪彩色热力图映射，使异常区域更直观。

    映射方案：
        - 低误差（冷色）：深蓝 → 绿
        - 中误差（暖色）：黄 → 橙
        - 高误差（热色）：红 → 白

    Args:
        gray_image: 灰度 ELA 图像（mode='L'）

    Returns:
        伪彩色 RGB 图像
    """
    gray_array = np.array(gray_image, dtype=np.float32) / 255.0

    # 使用 matplotlib 风格的热力图颜色映射（不需要依赖 matplotlib）
    # 分段线性插值实现 jet-like colormap
    r = np.zeros_like(gray_array)
    g = np.zeros_like(gray_array)
    b = np.zeros_like(gray_array)

    # 分段1: 0.0 - 0.125  深蓝 → 蓝
    mask1 = gray_array <= 0.125
    t1 = gray_array[mask1] / 0.125
    b[mask1] = 0.5 + 0.5 * t1
    g[mask1] = 0.0
    r[mask1] = 0.0

    # 分段2: 0.125 - 0.375  蓝 → 青
    mask2 = (gray_array > 0.125) & (gray_array <= 0.375)
    t2 = (gray_array[mask2] - 0.125) / 0.25
    r[mask2] = 0.0
    g[mask2] = t2
    b[mask2] = 1.0

    # 分段3: 0.375 - 0.625  青 → 绿 → 黄
    mask3 = (gray_array > 0.375) & (gray_array <= 0.625)
    t3 = (gray_array[mask3] - 0.375) / 0.25
    r[mask3] = t3
    g[mask3] = 1.0
    b[mask3] = 1.0 - t3

    # 分段4: 0.625 - 0.875  黄 → 红
    mask4 = (gray_array > 0.625) & (gray_array <= 0.875)
    t4 = (gray_array[mask4] - 0.625) / 0.25
    r[mask4] = 1.0
    g[mask4] = 1.0 - t4
    b[mask4] = 0.0

    # 分段5: 0.875 - 1.0    红 → 白
    mask5 = gray_array > 0.875
    t5 = (gray_array[mask5] - 0.875) / 0.125
    r[mask5] = 1.0
    g[mask5] = t5
    b[mask5] = t5

    # 合成 RGB 图像
    rgb_array = np.stack([
        (r * 255).astype(np.uint8),
        (g * 255).astype(np.uint8),
        (b * 255).astype(np.uint8),
    ], axis=2)

    return Image.fromarray(rgb_array, mode="RGB")
