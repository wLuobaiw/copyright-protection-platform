"""
证据打包模块 - C 负责实现

组装证据包并打包为ZIP：
    1. 将 metadata / verification_result / audit_log 写入JSON文件
    2. 对所有文件（含嫌疑文件）计算哈希，写入 hashes.json
    3. 全部打包为 ZIP
    4. 计算 ZIP 的 SHA-256

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

    压缩包内容：
        - 嫌疑文件（原始文件名保留）
        - metadata.json      取证元信息
        - hashes.json        所有文件哈希清单
        - verification_report.json  鉴定报告
        - audit_log.json     全流程操作审计日志
    """
    try:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        pkg_name = f"evidence_{timestamp}"
        pkg_dir = os.path.join(output_dir, pkg_name)
        os.makedirs(pkg_dir, exist_ok=True)

        # 1. 拷贝嫌疑文件
        suspect_name = os.path.basename(suspect_file)
        suspect_dst = os.path.join(pkg_dir, suspect_name)
        shutil.copy2(suspect_file, suspect_dst)

        # 2. 写入 metadata.json
        metadata_path = os.path.join(pkg_dir, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        # 3. 写入 verification_report.json
        conclusion = verification_result.get("conclusion", {})
        report_path = os.path.join(pkg_dir, "verification_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(conclusion, f, ensure_ascii=False, indent=2)

        # 4. 写入 audit_log.json
        audit_path = os.path.join(pkg_dir, "audit_log.json")
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(audit_log, f, ensure_ascii=False, indent=2)

        # 5. 对所有文件计算哈希，写入 hashes.json
        file_list = [suspect_dst, metadata_path, report_path, audit_path]
        hashes = {"files": [], "package_sha256": ""}
        for fp in file_list:
            hashes["files"].append({
                "name": os.path.basename(fp),
                "sha256": compute_sha256(fp),
                "md5": compute_md5(fp),
            })

        hashes_path = os.path.join(pkg_dir, "hashes.json")
        with open(hashes_path, "w", encoding="utf-8") as f:
            json.dump(hashes, f, ensure_ascii=False, indent=2)

        # 6. 打包为 ZIP
        zip_path = os.path.join(output_dir, f"{pkg_name}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(pkg_dir):
                for fn in files:
                    fp = os.path.join(root, fn)
                    arcname = os.path.relpath(fp, pkg_dir)
                    zf.write(fp, arcname)

        # 7. 计算 ZIP 的哈希
        pkg_hash = compute_sha256(zip_path)

        # 更新 hashes.json 中的 package_sha256
        hashes["package_sha256"] = pkg_hash
        with open(hashes_path, "w", encoding="utf-8") as f:
            json.dump(hashes, f, ensure_ascii=False, indent=2)

        # 重新打包（因为 hashes.json 更新了）
        os.remove(zip_path)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(pkg_dir):
                for fn in files:
                    fp = os.path.join(root, fn)
                    arcname = os.path.relpath(fp, pkg_dir)
                    zf.write(fp, arcname)

        # 最终 ZIP 哈希（因为内容变了，需要重新计算）
        pkg_hash = compute_sha256(zip_path)

        # 清理临时目录
        shutil.rmtree(pkg_dir)

        return {
            "success": True,
            "package_path": zip_path,
            "package_sha256": pkg_hash,
            "files": hashes["files"],
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
