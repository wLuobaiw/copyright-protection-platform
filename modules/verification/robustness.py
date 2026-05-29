"""
水印鲁棒性测试模块 - D 负责

对嵌入水印的图片施加多种攻击，测试水印在不同条件下的可提取性。
生成鲁棒性矩阵，用于评估水印方案的实际抗攻击能力。

接口约定：
    run_robustness_test(image_path, expected_watermark)
    -> {"success": bool, "results": [...], "summary": {...}}
"""

import os
import tempfile
import time

import cv2
import numpy as np


def _imread(path: str):
    """cv2.imread 在 Windows 上不支持中文路径，用 imdecode 绕过"""
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _imwrite(path: str, img: np.ndarray) -> bool:
    """cv2.imwrite 在 Windows 上不支持中文路径，用 imencode + tofile 绕过"""
    ext = os.path.splitext(path)[1]
    success, buf = cv2.imencode(ext, img)
    if success:
        buf.tofile(path)
    return success

from modules.steganography.extract import extract_watermark

# 攻击参数配置
JPEG_QUALITIES = [100, 90, 70, 50, 30, 10]
NOISE_SIGMAS = [1, 3, 5, 10, 15]
BLUR_KERNELS = [3, 5, 7, 9]
SCALE_RATIOS = [0.75, 0.5, 0.25]
CROP_RATIOS = [0.1, 0.25, 0.5]
BRIGHTNESS_DELTAS = [-40, -20, 20, 40]


# ---------------------------------------------------------------------------
# 攻击函数：输入图像数组，返回攻击后的图像数组
# ---------------------------------------------------------------------------

def _attack_jpeg(img: np.ndarray, quality: int) -> np.ndarray:
    """JPEG 重压缩攻击"""
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def _attack_noise(img: np.ndarray, sigma: float) -> np.ndarray:
    """高斯加性噪声攻击"""
    noise = np.random.normal(0, sigma, img.shape).astype(np.float32)
    noisy = img.astype(np.float32) + noise
    return np.clip(noisy, 0, 255).astype(np.uint8)


def _attack_blur(img: np.ndarray, kernel: int) -> np.ndarray:
    """高斯模糊攻击"""
    return cv2.GaussianBlur(img, (kernel, kernel), 0)


def _attack_scale(img: np.ndarray, ratio: float) -> np.ndarray:
    """缩放攻击：缩小后再放大回原尺寸"""
    h, w = img.shape[:2]
    small = cv2.resize(img, (int(w * ratio), int(h * ratio)))
    return cv2.resize(small, (w, h))


def _attack_crop(img: np.ndarray, ratio: float) -> np.ndarray:
    """中心裁剪攻击：裁掉四周 ratio 比例的内容后放大回原尺寸"""
    h, w = img.shape[:2]
    ch, cw = int(h * (1 - ratio)), int(w * (1 - ratio))
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    cropped = img[y0:y0 + ch, x0:x0 + cw]
    return cv2.resize(cropped, (w, h))


def _attack_brightness(img: np.ndarray, delta: int) -> np.ndarray:
    """亮度调整攻击"""
    return np.clip(img.astype(np.int16) + delta, 0, 255).astype(np.uint8)


# 攻击注册表
ATTACKS = [
    ("JPEG压缩",    _attack_jpeg,       JPEG_QUALITIES),
    ("高斯噪声",    _attack_noise,      NOISE_SIGMAS),
    ("高斯模糊",    _attack_blur,       BLUR_KERNELS),
    ("缩放",        _attack_scale,      SCALE_RATIOS),
    ("中心裁剪",    _attack_crop,       CROP_RATIOS),
    ("亮度调整",    _attack_brightness, BRIGHTNESS_DELTAS),
]


def run_robustness_test(image_path: str, expected_watermark: str = None) -> dict:
    """
    对指定图片执行水印鲁棒性测试。

    测试流程：
        1. 先对原图（无攻击）做一次基准提取
        2. 依次施加每种攻击 × 每个等级
        3. 每次攻击后调用 extract_watermark() 尝试提取
        4. 汇总结果，计算各攻击类型的生存率

    Args:
        image_path: 含水印的图片路径
        expected_watermark: 预期水印内容（可选，用于精确匹配校验）

    Returns:
        {
            "success": bool,
            "image_path": str,
            "expected_watermark": str,
            "baseline": {"extracted": str, "confidence": float, "match": bool},
            "results": [
                {
                    "attack": str,       # 攻击类型
                    "level": str,        # 攻击等级（人类可读）
                    "level_value": any,  # 攻击参数值
                    "extracted": str,    # 提取到的水印（None 表示失败）
                    "confidence": float, # 提取置信度
                    "match": bool,       # 是否与预期值匹配
                    "survived": bool,    # 水印是否存活
                },
                ...
            ],
            "summary": {
                "total_tests": int,
                "survived": int,
                "survival_rate": float,       # 0.0 ~ 1.0
                "per_attack_summary": [
                    {"attack": str, "survived": int, "total": int, "rate": float},
                    ...
                ],
            },
        }
    """
    if not os.path.isfile(image_path):
        return {"success": False, "message": f"文件不存在: {image_path}"}

    img = _imread(image_path)
    if img is None:
        return {"success": False, "message": f"无法读取图片: {image_path}"}

    results = []

    # ---- 基准测试（无攻击）----
    baseline = {"extracted": None, "confidence": 0.0, "match": False}
    baseline_result = extract_watermark(image_path)
    if baseline_result.get("success"):
        baseline["extracted"] = baseline_result.get("watermark")
        baseline["confidence"] = baseline_result.get("confidence", 0)
        if expected_watermark and baseline["extracted"]:
            baseline["match"] = (baseline["extracted"].strip()
                                 == expected_watermark.strip())

    # ---- 遍历所有攻击类型 ----
    tmp_dir = tempfile.mkdtemp(prefix="robustness_")

    try:
        for attack_name, attack_fn, levels in ATTACKS:
            for level in levels:
                entry = {
                    "attack": attack_name,
                    "level": str(level),
                    "level_value": level,
                    "extracted": None,
                    "confidence": 0.0,
                    "match": False,
                    "survived": False,
                }

                try:
                    # 施加攻击
                    attacked = attack_fn(img, level)

                    # 保存为临时文件供 extract_watermark 读取
                    tmp_path = os.path.join(
                        tmp_dir,
                        f"attacked_{attack_name}_{level}.png",
                    )
                    _imwrite(tmp_path, attacked)

                    # 尝试提取水印
                    ext_result = extract_watermark(tmp_path)
                    if ext_result.get("success"):
                        extracted_text = ext_result.get("watermark")
                        entry["extracted"] = extracted_text
                        entry["confidence"] = ext_result.get("confidence", 0)
                        entry["survived"] = bool(extracted_text)

                        if expected_watermark and extracted_text:
                            entry["match"] = (
                                extracted_text.strip()
                                == expected_watermark.strip()
                            )
                except Exception:
                    pass  # 攻击失败则标记为未存活
                finally:
                    # 清理临时文件
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass

                results.append(entry)

    finally:
        # 清理临时目录
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass

    # ---- 汇总统计 ----
    survived = sum(1 for r in results if r["survived"])
    total = len(results)
    survival_rate = survived / total if total > 0 else 0.0

    per_attack = []
    for attack_name, _, _ in ATTACKS:
        group = [r for r in results if r["attack"] == attack_name]
        group_survived = sum(1 for r in group if r["survived"])
        per_attack.append({
            "attack": attack_name,
            "survived": group_survived,
            "total": len(group),
            "rate": group_survived / len(group) if group else 0.0,
        })

    return {
        "success": True,
        "image_path": image_path,
        "expected_watermark": expected_watermark,
        "baseline": baseline,
        "results": results,
        "summary": {
            "total_tests": total,
            "survived": survived,
            "survival_rate": round(survival_rate, 4),
            "per_attack_summary": per_attack,
        },
    }
