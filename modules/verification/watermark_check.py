"""
水印校验模块 - D 负责实现

从嫌疑文件中提取水印，与原始版权信息比对。

接口约定：
    check_watermark(image_path, expected_watermark)
    -> {"extracted": str, "match": bool, "detail": str}
"""

from modules.steganography.extract import extract_watermark


def check_watermark(image_path: str, expected_watermark: str = None) -> dict:
    """
    提取水印并与预期值比对。

    TODO: D同学可在此增强校验逻辑。
    """
    result = extract_watermark(image_path)

    extracted = result.get("watermark") if result["success"] else None
    match = False
    detail = ""

    if extracted and expected_watermark:
        match = (extracted.strip() == expected_watermark.strip())
        detail = "水印匹配" if match else f"水印不匹配：预期'{expected_watermark}'，实际'{extracted}'"
    elif extracted:
        detail = f"已提取水印：{extracted}（未提供预期值，无法比对）"
    else:
        detail = "未能提取到水印"

    return {
        "extracted": extracted,
        "match": match,
        "detail": detail,
    }
