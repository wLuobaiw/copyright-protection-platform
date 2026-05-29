"""
水印鲁棒性测试模块 - Flask 蓝图

提供含水印图片上传 + 多种攻击测试 + 提取验证的完整流程。
"""

import io
import json
import os
import time
import uuid

import cv2
import numpy as np
from PIL import Image
from flask import Blueprint, render_template, request, jsonify

import config
from modules.steganography.extract import extract_watermark

robustness_bp = Blueprint("robustness", __name__, url_prefix="/robustness")

# 会话数据（内存）
_robustness_sessions = {}

# 测试结果暂存目录
ROBUSTNESS_TEST_DIR = os.path.join(config.DATA_DIR, "robustness_tests")


def _apply_jpeg_compression(image_path: str, quality: int) -> str:
    """JPEG 压缩攻击"""
    img = Image.open(image_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    attacked = Image.open(buf)
    out_path = _tmp_path("jpeg", quality)
    attacked.save(out_path, "PNG")
    return out_path


def _apply_resize_attack(image_path: str, scale: float) -> str:
    """缩放攻击：缩小后再放大回原尺寸"""
    img = cv2.imread(image_path)
    h, w = img.shape[:2]
    small = cv2.resize(img, (int(w * scale), int(h * scale)))
    restored = cv2.resize(small, (w, h))
    out_path = _tmp_path("resize", scale)
    cv2.imwrite(out_path, restored)
    return out_path


def _apply_crop_attack(image_path: str, ratio: float) -> str:
    """裁剪攻击：裁掉四周"""
    img = cv2.imread(image_path)
    h, w = img.shape[:2]
    ch, cw = int(h * ratio), int(w * ratio)
    cropped = img[ch:h - ch, cw:w - cw]
    out_path = _tmp_path("crop", ratio)
    cv2.imwrite(out_path, cropped)
    return out_path


def _apply_rotation_attack(image_path: str, angle: float) -> str:
    """旋转攻击"""
    img = cv2.imread(image_path)
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(img, matrix, (w, h), borderMode=cv2.BORDER_REFLECT)
    out_path = _tmp_path("rotate", angle)
    cv2.imwrite(out_path, rotated)
    return out_path


def _apply_noise_attack(image_path: str, sigma: float) -> str:
    """高斯噪声攻击"""
    img = cv2.imread(image_path)
    noise = np.random.normal(0, sigma, img.shape).astype(np.float32)
    noisy = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    out_path = _tmp_path("noise", sigma)
    cv2.imwrite(out_path, noisy)
    return out_path


def _tmp_path(attack_type: str, param) -> str:
    """生成攻击后图片临时路径"""
    os.makedirs(ROBUSTNESS_TEST_DIR, exist_ok=True)
    ts = int(time.time() * 1000)
    return os.path.join(ROBUSTNESS_TEST_DIR, f"{attack_type}_{param}_{ts}.png")


@robustness_bp.route("/")
def robustness_page():
    """鲁棒性测试页面"""
    return render_template("robustness.html")


@robustness_bp.route("/api/robustness/upload", methods=["POST"])
def upload_for_test():
    """上传含水印图片"""
    file = request.files.get("file")
    if not file:
        return jsonify({"success": False, "message": "请提供图片文件"}), 400

    session_id = uuid.uuid4().hex[:16]
    ext = os.path.splitext(file.filename)[1] or ".png"
    img_path = os.path.join(ROBUSTNESS_TEST_DIR, f"{session_id}_original{ext}")
    os.makedirs(ROBUSTNESS_TEST_DIR, exist_ok=True)
    file.save(img_path)

    _robustness_sessions[session_id] = {
        "image_path": img_path,
        "watermark_text": "",
        "original_filename": file.filename,
    }

    return jsonify({
        "success": True,
        "session_id": session_id,
        "filename": file.filename,
    })


@robustness_bp.route("/api/robustness/test", methods=["POST"])
def run_test():
    """执行全部攻击测试"""
    data = request.get_json()
    session_id = data.get("session_id")
    watermark_text = data.get("watermark_text", "").strip()
    if not session_id or session_id not in _robustness_sessions:
        return jsonify({"success": False, "message": "会话不存在，请先上传文件"}), 400
    if not watermark_text:
        return jsonify({"success": False, "message": "请输入原始水印文本"}), 400

    session = _robustness_sessions[session_id]
    img_path = session["image_path"]
    expected_wm = watermark_text

    # 定义所有攻击
    attacks = [
        {"type": "JPEG 压缩", "params": [{"quality": q} for q in [10, 30, 50, 70, 90]],
         "func": _apply_jpeg_compression, "arg_key": "quality"},
        {"type": "缩放攻击", "params": [{"scale": s} for s in [0.1, 0.3, 0.5, 0.7, 0.9]],
         "func": _apply_resize_attack, "arg_key": "scale"},
        {"type": "裁剪攻击", "params": [{"ratio": r} for r in [0.05, 0.10, 0.20, 0.30]],
         "func": _apply_crop_attack, "arg_key": "ratio"},
        {"type": "旋转攻击", "params": [{"angle": a} for a in [1, 3, 5, 10, 15]],
         "func": _apply_rotation_attack, "arg_key": "angle"},
        {"type": "噪声攻击", "params": [{"sigma": s} for s in [5, 10, 15, 20, 25]],
         "func": _apply_noise_attack, "arg_key": "sigma"},
    ]

    results = []

    for attack in attacks:
        for param_dict in attack["params"]:
            attack_name = attack["type"]
            arg_val = list(param_dict.values())[0]
            arg_label = f"{list(param_dict.keys())[0]}={arg_val}"

            try:
                # 执行攻击
                attacked_path = attack["func"](img_path, **param_dict)

                # 提取水印
                extract_result = extract_watermark(attacked_path)
                extracted = extract_result.get("watermark") if extract_result.get("success") else None
                confidence = extract_result.get("confidence", 0)

                # 判断是否匹配（精确匹配或子串匹配都算）
                matched = False
                match_type = "无"
                if extracted:
                    ext = extracted.strip()
                    exp = expected_wm.strip()
                    if ext == exp:
                        matched = True
                        match_type = "精确匹配"
                    elif exp in ext or ext in exp:
                        matched = True
                        match_type = "子串匹配"

                results.append({
                    "attack_type": attack_name,
                    "parameter": arg_label,
                    "extracted": extracted,
                    "matched": matched,
                    "match_type": match_type,
                    "confidence": confidence,
                })
            except Exception as e:
                results.append({
                    "attack_type": attack_name,
                    "parameter": arg_label,
                    "extracted": None,
                    "matched": False,
                    "match_type": "无",
                    "confidence": 0,
                    "error": str(e),
                })

    # 统计
    total = len(results)
    success_count = sum(1 for r in results if r["matched"])
    robustness_score = round(success_count / total * 100, 1) if total > 0 else 0

    return jsonify({
        "success": True,
        "results": results,
        "summary": {
            "total_tests": total,
            "success_count": success_count,
            "fail_count": total - success_count,
            "robustness_score": robustness_score,
        },
    })