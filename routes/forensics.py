import json
import os
import time
import uuid

from flask import Blueprint, render_template, request, jsonify, send_file

import config
from modules.forensics.hasher import compute_sha256
from modules.forensics.metadata import create_metadata_json
from modules.forensics.packager import build_evidence_package
from modules.verification.validator import run_identification
from modules.verification.robustness import run_robustness_test

forensics_bp = Blueprint("forensics", __name__, url_prefix="/forensics")

# 内存中暂存当前会话的鉴定结果（生产环境应改用 session 或数据库）
_session_data = {}


@forensics_bp.route("/")
def forensics_page():
    """页面3：侵权取证与鉴定"""
    return render_template("forensics.html")


@forensics_bp.route("/api/forensics/upload", methods=["POST"])
def upload_suspect():
    """第1步：上传嫌疑文件"""
    file = request.files.get("file")
    if not file:
        return jsonify({"success": False, "message": "请选择文件"}), 400

    session_id = uuid.uuid4().hex[:16]
    ext = os.path.splitext(file.filename)[1] or ".png"
    suspect_path = os.path.join(config.EVIDENCE_DIR, f"{session_id}_suspect{ext}")
    file.save(suspect_path)

    _session_data[session_id] = {
        "suspect_path": suspect_path,
        "original_filename": file.filename,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    return jsonify({
        "success": True,
        "session_id": session_id,
        "filename": file.filename,
    })


@forensics_bp.route("/api/forensics/identify", methods=["POST"])
def identify():
    """第2+3步：接收元信息 + 执行鉴定"""
    session_id = request.form.get("session_id")
    if not session_id or session_id not in _session_data:
        return jsonify({"success": False, "message": "会话不存在，请先上传文件"}), 400

    session = _session_data[session_id]
    suspect_path = session["suspect_path"]

    # 生成元信息
    metadata = create_metadata_json(
        source_url=request.form.get("source_url", ""),
        capture_time=request.form.get("capture_time", ""),
        publisher=request.form.get("publisher", ""),
        notes=request.form.get("notes", ""),
        officer=request.form.get("officer", "取证员"),
    )

    # 执行鉴定（调用 D 的模块）
    expected_watermark = request.form.get("expected_watermark", None)
    verification_result = run_identification(suspect_path, expected_watermark)

    # 暂存结果，供后续打包使用
    session["metadata"] = metadata
    session["verification_result"] = verification_result
    _session_data[session_id] = session

    # 生成 ELA 图片的访问 URL
    ela_image_path = verification_result.get("ela_image")
    ela_image_url = None
    if ela_image_path and os.path.exists(ela_image_path):
        ela_filename = os.path.basename(ela_image_path)
        ela_image_url = f"/forensics/api/forensics/ela-image/{session_id}/{ela_filename}"

    return jsonify({
        "success": verification_result["success"],
        "log": verification_result["log"],
        "conclusion": verification_result["conclusion"],
        "ela_image_url": ela_image_url,
    })


@forensics_bp.route("/api/forensics/package", methods=["POST"])
def package_evidence():
    """第4步：打包证据 ZIP"""
    data = request.get_json()
    session_id = data.get("session_id")
    if not session_id or session_id not in _session_data:
        return jsonify({"success": False, "message": "会话不存在"}), 400

    session = _session_data[session_id]

    result = build_evidence_package(
        suspect_file=session["suspect_path"],
        metadata=session.get("metadata", {}),
        verification_result=session.get("verification_result", {}),
        audit_log=session.get("verification_result", {}).get("log", []),
        output_dir=config.EVIDENCE_DIR,
    )

    if result.get("success"):
        session["package_path"] = result["package_path"]
        session["package_sha256"] = result["package_sha256"]
        _session_data[session_id] = session

    return jsonify(result)


@forensics_bp.route("/api/forensics/download/<session_id>")
def download_evidence(session_id):
    """下载证据压缩包"""
    if session_id not in _session_data:
        return jsonify({"success": False, "message": "会话不存在"}), 404

    session = _session_data[session_id]
    package_path = session.get("package_path")
    if not package_path or not os.path.exists(package_path):
        return jsonify({"success": False, "message": "请先生成证据包"}), 400

    return send_file(
        package_path,
        as_attachment=True,
        download_name=os.path.basename(package_path),
    )


@forensics_bp.route("/api/forensics/ela-image/<session_id>/<filename>")
def serve_ela_image(session_id, filename):
    """提供 ELA 分析结果图的访问"""
    if session_id not in _session_data:
        return jsonify({"success": False, "message": "会话不存在"}), 404

    session = _session_data[session_id]
    verification_result = session.get("verification_result", {})
    ela_image_path = verification_result.get("ela_image")

    if not ela_image_path or not os.path.exists(ela_image_path):
        return jsonify({"success": False, "message": "ELA图片不存在"}), 404

    return send_file(ela_image_path, mimetype="image/png")


@forensics_bp.route("/api/forensics/robustness", methods=["POST"])
def robustness_test():
    """水印鲁棒性测试：对已上传的嫌疑文件施加多种攻击，测试水印存活率"""
    session_id = request.form.get("session_id")
    if not session_id or session_id not in _session_data:
        return jsonify({"success": False, "message": "会话不存在，请先上传文件"}), 400

    suspect_path = _session_data[session_id]["suspect_path"]
    expected_watermark = request.form.get("expected_watermark", None)

    result = run_robustness_test(suspect_path, expected_watermark)

    # 暂存到会话，供后续打包时附带
    _session_data[session_id]["robustness_result"] = result

    return jsonify(result)
