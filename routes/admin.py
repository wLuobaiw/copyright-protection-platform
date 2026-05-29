import json
import os
import shutil
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

    # 嵌入水印 —— 直接输出到 uploads 目录供前端访问
    watermarked_filename = f"{unique_id}_wm{ext}"
    watermarked_path = os.path.join(config.UPLOADS_DIR, watermarked_filename)
    # 同时保留一份到 watermarked 目录做存档
    archive_path = os.path.join(config.WATERMARKED_DIR, watermarked_filename)
    result = embed_watermark(original_path, watermark_text, watermarked_path)

    if not result["success"]:
        return jsonify(result), 500

    # 存档副本（发布时可能用到）
    if watermarked_path != archive_path:
        shutil.copy2(watermarked_path, archive_path)

    # 自验证：从嵌入后的图中提取水印
    verify = extract_watermark(watermarked_path)

    return jsonify({
        "success": True,
        "work_id": unique_id,
        "original_name": file.filename,
        "psnr": result.get("psnr"),
        "watermark_verified": verify.get("watermark") if verify["success"] else None,
        "watermarked_url": f"/static/uploads/{watermarked_filename}",
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
        shutil.copy2(src, dst)

    # 更新作品列表
    works_data = {"works": []}
    if os.path.exists(config.WORKS_JSON):
        with open(config.WORKS_JSON, "r", encoding="utf-8") as f:
            works_data = json.load(f)

    # 取出现有作品列表（兼容旧格式），追加新作品
    works_list = works_data.get("works", [])
    works_list.append({
        "id": work_id,
        "original_name": original_name,
        "watermark": watermark_text,
        "image": f"/static/uploads/{watermarked_filename}",
        "published_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })

    with open(config.WORKS_JSON, "w", encoding="utf-8") as f:
        json.dump({"works": works_list}, f, ensure_ascii=False, indent=2)

    return jsonify({"success": True, "message": "发布成功"})


@admin_bp.route("/api/admin/works")
def list_works():
    """获取已管理作品列表"""
    if not os.path.exists(config.WORKS_JSON):
        return jsonify({"works": []})
    with open(config.WORKS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)


@admin_bp.route("/api/admin/works/<work_id>", methods=["DELETE"])
def delete_work(work_id):
    """从作品列表中删除指定作品，同时清理关联图片文件"""
    if not os.path.exists(config.WORKS_JSON):
        return jsonify({"success": False, "message": "作品列表为空"}), 404

    with open(config.WORKS_JSON, "r", encoding="utf-8") as f:
        works_data = json.load(f)

    works_list = works_data.get("works", [])
    # 找到要删除的作品（记录其图片路径以便清理文件）
    target = next((w for w in works_list if w.get("id") == work_id), None)
    if target is None:
        return jsonify({"success": False, "message": "作品不存在"}), 404

    # 尝试删除关联的图片文件（uploads 目录下的副本）
    image_path = target.get("image", "")
    if image_path.startswith("/static/uploads/"):
        file_to_delete = os.path.join(config.UPLOADS_DIR, os.path.basename(image_path))
        if os.path.exists(file_to_delete):
            try:
                os.remove(file_to_delete)
            except OSError:
                pass  # 文件删除失败不影响记录删除

    # 过滤掉被删除的作品，写回
    new_works = [w for w in works_list if w.get("id") != work_id]
    with open(config.WORKS_JSON, "w", encoding="utf-8") as f:
        json.dump({"works": new_works}, f, ensure_ascii=False, indent=2)

    return jsonify({"success": True, "message": "作品已删除"})
