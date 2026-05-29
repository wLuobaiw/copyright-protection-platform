"""
证据打包模块 - C 负责实现

组装证据包并打包为ZIP：
    1. 对输入文件做哈希校验
    2. 将 metadata / verification_result / audit_log 写入JSON文件
    3. 对所有文件（含嫌疑文件）计算哈希，写入 hashes.json
    4. 全部打包为 ZIP
    5. 计算 ZIP 的 SHA-256，写入同级 .sha256 文件

接口约定：
    build_evidence_package(suspect_file, metadata, verification_result, audit_log, output_dir)
    -> {"success": bool, "package_path": str, "package_sha256": str, "files": list}
"""

import json
import os
import shutil
import time
import zipfile

from modules.forensics.hasher import compute_sha256, compute_md5


def build_evidence_package(
    suspect_file: str,
    metadata: dict,
    verification_result: dict,
    audit_log: list,
    output_dir: str,
) -> dict:
    """
    组装证据包并打包为ZIP。

    流程：
        1. 校验输入 → 2. 写入各 JSON → 3. 计算所有文件哈希 → 4. 打包 → 5. 校验ZIP

    压缩包内容：
        - 嫌疑文件（原始文件名保留）
        - metadata.json      取证元信息
        - hashes.json        所有文件哈希清单
        - verification_report.json  完整鉴定报告
        - audit_log.json     全流程操作审计日志
    """
    # ---- 1. 输入校验 ----
    if not os.path.isfile(suspect_file):
        return {"success": False, "message": f"嫌疑文件不存在：{suspect_file}"}

    try:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        pkg_name = f"evidence_{timestamp}"
        pkg_dir = os.path.join(output_dir, pkg_name)
        os.makedirs(pkg_dir, exist_ok=True)

        # ---- 2. 拷贝嫌疑文件 ----
        suspect_name = os.path.basename(suspect_file)
        suspect_dst = os.path.join(pkg_dir, suspect_name)
        shutil.copy2(suspect_file, suspect_dst)

        # ---- 3. 写入各 JSON 文件 ----
        # metadata.json
        metadata_path = os.path.join(pkg_dir, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        # verification_report.json —— 写入完整鉴定结果（含 success / log / conclusion）
        report_path = os.path.join(pkg_dir, "verification_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(verification_result, f, ensure_ascii=False, indent=2)

        # audit_log.json —— 操作审计轨迹，与鉴定报告分开存放
        audit_path = os.path.join(pkg_dir, "audit_log.json")
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(audit_log, f, ensure_ascii=False, indent=2)

        # ---- 4. 计算所有文件哈希 → hashes.json ----
        # hashes.json 仅记录包内文件哈希，不含 ZIP 自身哈希（鸡生蛋问题）
        file_list = [suspect_dst, metadata_path, report_path, audit_path]
        hashes_files = []
        for fp in file_list:
            hashes_files.append({
                "name": os.path.basename(fp),
                "sha256": compute_sha256(fp),
                "md5": compute_md5(fp),
            })

        hashes_path = os.path.join(pkg_dir, "hashes.json")
        hashes_data = {"files": hashes_files}
        with open(hashes_path, "w", encoding="utf-8") as f:
            json.dump(hashes_data, f, ensure_ascii=False, indent=2)

        # ---- 5. 打包为 ZIP ----
        zip_path = os.path.join(output_dir, f"{pkg_name}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(pkg_dir):
                for fn in files:
                    fp = os.path.join(root, fn)
                    arcname = os.path.relpath(fp, pkg_dir)
                    zf.write(fp, arcname)

        # ---- 6. 计算 ZIP 哈希，写入同级 .sha256 文件 ----
        pkg_hash = compute_sha256(zip_path)
        sha256_path = zip_path + ".sha256"
        with open(sha256_path, "w", encoding="utf-8") as f:
            f.write(f"{pkg_hash}  {os.path.basename(zip_path)}\n")

        # ---- 7. 清理临时目录 ----
        shutil.rmtree(pkg_dir)

        return {
            "success": True,
            "package_path": zip_path,
            "package_sha256": pkg_hash,
            "files": hashes_files,
        }

    except Exception as e:
        # 发生异常时尝试清理临时目录
        try:
            if os.path.isdir(pkg_dir):
                shutil.rmtree(pkg_dir)
        except Exception:
            pass
        return {"success": False, "message": str(e)}
