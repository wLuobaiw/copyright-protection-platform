"""
综合鉴定器 - D 负责实现

串联全部检验步骤：SHA-256 → ELA → 水印提取 → 水印比对 → 综合判定
返回完整的鉴定日志、结论和证据文件路径。

接口约定：
    run_identification(suspect_file, expected_watermark)
    -> {"success": bool, "log": [...], "conclusion": {...},
        "ela_image": str|None, "verification_report_path": str|None}
"""

import json
import os
import time

import config
from modules.forensics.hasher import compute_sha256
from modules.verification.ela import ela_analysis
from modules.verification.watermark_check import check_watermark


# 鉴定结论等级
JUDGMENT_SUPPORTED = "supported"     # 技术鉴定支持侵权认定
JUDGMENT_SUSPICIOUS = "suspicious"   # 存在疑点，需人工复核
JUDGMENT_INCONCLUSIVE = "inconclusive"  # 证据不足，无法认定
JUDGMENT_ERROR = "error"             # 鉴定过程异常


def run_identification(suspect_file: str, expected_watermark: str = None) -> dict:
    """
    执行完整的鉴定流程，返回逐步骤日志和最终结论。

    鉴定步骤：
        1. SHA-256 哈希计算 —— 文件唯一标识与完整性校验
        2. ELA 误差水平分析 —— 检测图片是否存在篡改/合成痕迹
        3. 水印提取 —— 从文件中提取隐含的版权水印
        4. 水印比对 —— 将提取的水印与原始版权信息比对
        5. 综合判定 —— 综合所有证据给出最终鉴定意见

    Args:
        suspect_file: 嫌疑文件路径
        expected_watermark: 预期版权水印内容（可选）

    Returns:
        dict: {
            "success": bool,
            "log": [{"step": str, "status": str, "detail": str, "timestamp": str}, ...],
            "conclusion": {
                "file_sha256": str,
                "ela_result": str,
                "ela_anomaly_detected": bool,
                "ela_anomaly_ratio": float,
                "watermark_extracted": str|None,
                "watermark_match": bool,
                "watermark_match_method": str,
                "watermark_similarity": float|None,
                "judgment_level": str,
                "final_judgment": str,
            },
            "ela_image": str|None,
        }
    """
    log = []
    conclusion = {}

    def _add_log(step, status, detail):
        log.append({
            "step": step,
            "status": status,
            "detail": detail,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    try:
        # ========== 步骤1：计算文件哈希 ==========
        _add_log("sha256", "running", "正在计算文件 SHA-256 哈希...")
        file_hash = compute_sha256(suspect_file)
        _add_log("sha256", "ok", file_hash)
        conclusion["file_sha256"] = file_hash

        # ========== 步骤2：ELA 篡改检测 ==========
        # 为 ELA 结果图生成输出路径
        ela_output_dir = os.path.join(config.REPORTS_DIR, "ela")
        os.makedirs(ela_output_dir, exist_ok=True)
        ela_image_name = f"ela_{file_hash[:12]}_{int(time.time())}.png"
        ela_output_path = os.path.join(ela_output_dir, ela_image_name)

        _add_log("ela", "running", "正在执行 ELA 误差水平分析...")
        ela_result = ela_analysis(suspect_file, output_ela_image=ela_output_path)
        ela_status = ela_result.get("status", "error")
        _add_log("ela", ela_status, ela_result.get("detail", "ELA分析完成"))

        conclusion["ela_result"] = ela_result.get("detail", "")
        conclusion["ela_anomaly_detected"] = ela_result.get("anomaly_detected", False)
        conclusion["ela_anomaly_ratio"] = ela_result.get("anomaly_ratio", 0.0)

        # 如果 ELA 图生成成功则记录路径，否则忽略
        ela_image = ela_output_path if os.path.exists(ela_output_path) else None

        # ========== 步骤3：水印提取 ==========
        _add_log("watermark_extract", "running", "正在从嫌疑文件中提取数字水印...")
        wm_result = check_watermark(suspect_file)
        extracted = wm_result.get("extracted")
        _add_log(
            "watermark_extract",
            "ok" if extracted else "fail",
            extracted or "未检测到水印",
        )
        conclusion["watermark_extracted"] = extracted

        # ========== 步骤4：水印比对 ==========
        _add_log("watermark_match", "running",
                 f"正在比对水印：预期='{expected_watermark or '(未提供)'}'")
        wm_match_result = check_watermark(suspect_file, expected_watermark)
        _add_log(
            "watermark_match",
            "ok" if wm_match_result.get("match") else "fail",
            wm_match_result.get("detail", ""),
        )
        conclusion["watermark_match"] = wm_match_result.get("match", False)
        conclusion["watermark_match_method"] = wm_match_result.get("method", "none")
        conclusion["watermark_similarity"] = wm_match_result.get("similarity")

        # ========== 步骤5：综合判定 ==========
        ela_anomaly = ela_result.get("anomaly_detected", False)
        wm_extracted = bool(extracted)
        wm_matched = wm_match_result.get("match", False)

        # 综合判定逻辑矩阵：
        #   ELA异常 + 水印匹配 → 强证据，支持侵权认定
        #   ELA异常 + 水印不匹配 → 可疑，可能水印被破坏
        #   ELA正常 + 水印匹配 → 支持侵权认定（仅水印证据）
        #   ELA正常 + 水印不匹配 → 证据不足
        #   仅水印提取（无预期值）→ 提供提取结果，无法判定

        if wm_extracted and wm_matched:
            if ela_anomaly:
                judgment_level = JUDGMENT_SUPPORTED
                judgment = (
                    "【技术鉴定支持侵权认定】"
                    "嫌疑文件中检测到与原始版权一致的水印信息，"
                    "且 ELA 分析发现图片存在篡改异常区域。"
                    "两项证据相互印证，强烈支持侵权认定。"
                )
            else:
                judgment_level = JUDGMENT_SUPPORTED
                judgment = (
                    "【技术鉴定支持侵权认定】"
                    "嫌疑文件中检测到与原始版权一致的水印信息。"
                    "ELA 分析未发现明显篡改痕迹，但水印匹配提供了关键证据。"
                )
        elif wm_extracted and not wm_matched:
            if ela_anomaly:
                judgment_level = JUDGMENT_SUSPICIOUS
                judgment = (
                    "【存在侵权嫌疑，需人工复核】"
                    "ELA 分析发现图片存在篡改异常区域，"
                    "但提取的水印与提供的原始版权信息不匹配。"
                    "可能原水印已被覆盖或破坏，建议人工审查原始作品与嫌疑文件的关联性。"
                )
            else:
                judgment_level = JUDGMENT_INCONCLUSIVE
                judgment = (
                    "【证据不足，无法认定】"
                    f"嫌疑文件中提取到的水印（'{extracted}'）"
                    "与提供的原始版权信息不匹配，且 ELA 未发现篡改痕迹。"
                    "建议核实原始版权信息是否正确，或结合其他非技术证据综合判断。"
                )
        elif not wm_extracted:
            if ela_anomaly:
                judgment_level = JUDGMENT_SUSPICIOUS
                judgment = (
                    "【存在侵权嫌疑，需人工复核】"
                    "ELA 分析发现图片存在篡改异常区域，"
                    "但未从文件中提取到水印信息。"
                    "图片可能经过剪裁、重压缩等处理导致水印丢失，"
                    "建议结合原件比对或元数据分析进一步确认。"
                )
            else:
                judgment_level = JUDGMENT_INCONCLUSIVE
                judgment = (
                    "【证据不足，无法认定】"
                    "嫌疑文件中未检测到水印，且 ELA 未发现明显篡改痕迹。"
                    "可能该文件从未嵌入水印，或水印因过度压缩/格式转换而丢失。"
                    "建议结合其他证据（如发布时间线、原件比对等）综合判断。"
                )
        else:
            judgment_level = JUDGMENT_INCONCLUSIVE
            judgment = "鉴定结果不明确，建议人工复核。"

        conclusion["judgment_level"] = judgment_level
        conclusion["final_judgment"] = judgment

        _add_log("complete", "ok", judgment)

        return {
            "success": True,
            "log": log,
            "conclusion": conclusion,
            "ela_image": ela_image,
        }

    except Exception as e:
        _add_log("error", "fail", str(e))
        conclusion["judgment_level"] = JUDGMENT_ERROR
        conclusion["final_judgment"] = f"鉴定过程发生异常：{e}"
        return {
            "success": False,
            "log": log,
            "conclusion": conclusion,
            "ela_image": None,
        }
