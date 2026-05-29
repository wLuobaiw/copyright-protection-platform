import json
import os
import time
import uuid

from flask import Blueprint, render_template, request, jsonify

import config
from modules.steganography.embed import embed_watermark
from modules.steganography.extract import extract_watermark

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
def admin_page():
    """页面2：作品管理（后台上传+水印嵌入）"""
    return render_template("admin.html")


@admin_bp.route("/api/admin/upload", methods=["POST"])
def upload_work():
    """上传原图 + 嵌入水印"""
    file = request.files.get("file")
    watermark_text = request.form.get("watermark", "").strip()
    if not file or not watermark_text:
        return jsonify({"success": False, "message": "缺少文件或版权信息"}), 400

    # 保存原始文件
    ext = os.path.splitext(file.filename)[1] or ".png"
    unique_id = uuid.uuid4().hex[:12]
    original_path = os.path.join(config.ORIGINALS_DIR, f"{unique_id}{ext}")
    file.save(original_path)

    # 嵌入水印
    watermarked_path = os.path.join(config.WATERMARKED_DIR, f"{unique_id}_wm{ext}")
    result = embed_watermark(original_path, watermark_text, watermarked_path)

    if not result["success"]:
        return jsonify(result), 500

    # 自验证：从嵌入后的图中提取水印
    verify = extract_watermark(watermarked_path)

    return jsonify({
        "success": True,
        "work_id": unique_id,
        "original_name": file.filename,
        "psnr": result.get("psnr"),
        "watermark_verified": verify.get("watermark") if verify["success"] else None,
        "watermarked_url": f"/static/uploads/{unique_id}_wm{ext}",
    })


@admin_bp.route("/api/admin/publish", methods=["POST"])
def publish_work():
    """发布作品到展示页"""
    data = request.get_json()
    work_id = data.get("work_id")
    watermark_text = data.get("watermark_text")
    original_name = data.get("original_name")
    watermarked_filename = data.get("watermarked_filename")

    if not all([work_id, watermark_text, watermarked_filename]):
        return jsonify({"success": False, "message": "参数不完整"}), 400

    # 将水印图复制到 uploads 目录供前端访问
    src = os.path.join(config.WATERMARKED_DIR, watermarked_filename)
    dst = os.path.join(config.UPLOADS_DIR, watermarked_filename)
    if os.path.exists(src):
        import shutil
        shutil.copy2(src, dst)

    # 更新作品列表
    works = {}
    if os.path.exists(config.WORKS_JSON):
        with open(config.WORKS_JSON, "r", encoding="utf-8") as f:
            works = json.load(f)

    works[work_id] = {
        "id": work_id,
        "original_name": original_name,
        "watermark": watermark_text,
        "image": f"/static/uploads/{watermarked_filename}",
        "published_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open(config.WORKS_JSON, "w", encoding="utf-8") as f:
        json.dump({"works": list(works.values())}, f, ensure_ascii=False, indent=2)

    return jsonify({"success": True, "message": "发布成功"})


@admin_bp.route("/api/admin/works")
def list_works():
    """获取已管理作品列表"""
    if not os.path.exists(config.WORKS_JSON):
        return jsonify({"works": []})
    with open(config.WORKS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)
