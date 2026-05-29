"""
水印校验模块 - D 负责实现

从嫌疑文件中提取水印，与原始版权信息比对。
支持精确匹配和模糊匹配（子串包含、编辑距离）。

接口约定：
    check_watermark(image_path, expected_watermark)
    -> {"extracted": str, "match": bool, "detail": str, "method": str,
        "similarity": float | None}
"""

from modules.steganography.extract import extract_watermark


def check_watermark(image_path: str, expected_watermark: str = None) -> dict:
    """
    提取水印并与预期值比对。

    校验策略（按优先级）：
        1. 精确匹配：提取的水印与预期值完全一致
        2. 子串匹配：提取的水印包含预期值，或预期值包含提取的水印
        3. 相似度匹配：基于编辑距离计算文本相似度，当相似度 >= 0.7 时视为近似匹配

    Args:
        image_path: 待检测图片路径
        expected_watermark: 预期的版权水印内容（可选）

    Returns:
        dict: {
            "extracted": str|None,    # 提取到的水印文本
            "match": bool,            # 是否匹配
            "detail": str,            # 详细说明
            "method": str,            # 匹配方式: "exact" / "substring" / "fuzzy" / "none"
            "similarity": float|None, # 相似度 (0.0~1.0)，仅模糊匹配时有值
        }
    """
    result = extract_watermark(image_path)

    extracted = result.get("watermark") if result["success"] else None
    match = False
    method = "none"
    similarity = None
    detail = ""

    if extracted and expected_watermark:
        extracted_norm = extracted.strip()
        expected_norm = expected_watermark.strip()

        # 策略1：精确匹配
        if extracted_norm == expected_norm:
            match = True
            method = "exact"
            detail = f"水印精确匹配：'{extracted_norm}'"
            similarity = 1.0

        # 策略2：子串包含匹配
        elif expected_norm in extracted_norm:
            match = True
            method = "substring"
            detail = f"水印部分匹配：提取值'{extracted_norm}'包含预期值'{expected_norm}'"
            similarity = len(expected_norm) / max(len(extracted_norm), 1)

        elif extracted_norm in expected_norm:
            match = True
            method = "substring"
            detail = f"水印部分匹配：预期值'{expected_norm}'包含提取值'{extracted_norm}'"
            similarity = len(extracted_norm) / max(len(expected_norm), 1)

        # 策略3：编辑距离模糊匹配
        else:
            sim = _text_similarity(extracted_norm, expected_norm)
            similarity = sim
            if sim >= 0.7:
                match = True
                method = "fuzzy"
                detail = (
                    f"水印模糊匹配（相似度 {sim:.1%}）："
                    f"预期'{expected_norm}'，实际'{extracted_norm}'"
                )
            else:
                match = False
                method = "none"
                detail = (
                    f"水印不匹配（相似度 {sim:.1%}）："
                    f"预期'{expected_watermark}'，实际'{extracted}'"
                )

    elif extracted:
        method = "none"
        detail = f"已提取水印：{extracted}（未提供预期值，无法比对）"
    else:
        method = "none"
        detail = "未能提取到水印"

    return {
        "extracted": extracted,
        "match": match,
        "detail": detail,
        "method": method,
        "similarity": similarity,
    }


def _text_similarity(s1: str, s2: str) -> float:
    """
    计算两个字符串的相似度（基于编辑距离）。

    使用 Levenshtein 距离归一化为 0.0~1.0 的相似度。
    1.0 表示完全相同，0.0 表示完全不同。

    Args:
        s1: 字符串1
        s2: 字符串2

    Returns:
        float: 相似度值，范围 [0.0, 1.0]
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    # 计算 Levenshtein 编辑距离
    m, n = len(s1), len(s2)
    # 使用滚动数组优化空间
    prev = list(range(n + 1))
    curr = [0] * (n + 1)

    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,        # 删除
                curr[j - 1] + 1,    # 插入
                prev[j - 1] + cost, # 替换
            )
        prev, curr = curr, prev

    distance = prev[n]
    max_len = max(m, n)
    return 1.0 - (distance / max_len)
