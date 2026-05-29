"""
综合鉴定器 - D 负责实现

串联全部检验步骤：SHA-256 → ELA → 水印提取 → 水印比对
返回完整的鉴定日志和结论。

接口约定：
    run_identification(suspect_file, expected_watermark)
    -> {"success": bool, "log": [...], "conclusion": {...}}
"""

import time

from modules.forensics.hasher import compute_sha256
from modules.verification.ela import ela_analysis
from modules.verification.watermark_check import check_watermark


def run_identification(suspect_file: str, expected_watermark: str = None) -> dict:
    """
    执行完整的鉴定流程，返回逐步骤日志和最终结论。

    TODO: D同学可在此增加更多检验步骤（如元数据分析、噪声分析等）。
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
        # 步骤1：计算文件哈希
        file_hash = compute_sha256(suspect_file)
        _add_log("sha256", "ok", file_hash)
        conclusion["file_sha256"] = file_hash

        # 步骤2：ELA 篡改检测
        ela_result = ela_analysis(suspect_file)
        _add_log("ela", ela_result["status"], ela_result["detail"])
        conclusion["ela_result"] = ela_result["detail"]

        # 步骤3：水印提取
        wm_result = check_watermark(suspect_file)
        extracted = wm_result["extracted"]
        _add_log(
            "watermark_extract",
            "ok" if extracted else "fail",
            extracted or "未检测到水印",
        )
        conclusion["watermark_extracted"] = extracted

        # 步骤4：水印比对
        wm_match_result = check_watermark(suspect_file, expected_watermark)
        _add_log(
            "watermark_match",
            "ok" if wm_match_result["match"] else "fail",
            wm_match_result["detail"],
        )
        conclusion["watermark_match"] = wm_match_result["match"]

        # 步骤5：综合判定
        if extracted and wm_match_result["match"]:
            conclusion["final_judgment"] = "技术鉴定支持侵权认定：嫌疑文件中检测到与原始版权一致的水印信息"
        elif extracted:
            conclusion["final_judgment"] = "嫌疑文件中检测到水印，但与提供的原始版权信息不匹配，需人工复核"
        else:
            conclusion["final_judgment"] = "嫌疑文件中未检测到水印，无法通过水印技术认定侵权，建议结合其他证据综合判断"

        _add_log("complete", "ok", conclusion["final_judgment"])

        return {"success": True, "log": log, "conclusion": conclusion}
    except Exception as e:
        _add_log("error", "fail", str(e))
        conclusion["final_judgment"] = f"鉴定过程异常：{e}"
        return {"success": False, "log": log, "conclusion": conclusion}
