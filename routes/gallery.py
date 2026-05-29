import json
import os

from flask import Blueprint, render_template, jsonify

import config

gallery_bp = Blueprint("gallery", __name__)


@gallery_bp.route("/")
def gallery_page():
    """页面1：作品展示画廊"""
    return render_template("gallery.html")


@gallery_bp.route("/api/gallery/works")
def get_works():
    """获取已发布的作品列表"""
    if not os.path.exists(config.WORKS_JSON):
        return jsonify({"works": []})
    with open(config.WORKS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)
