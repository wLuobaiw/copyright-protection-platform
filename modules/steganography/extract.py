"""steganography/extract.py —— 水印提取模块

基于DCT频域的盲水印提取（4象限独立解码 + 多副本表决）

抗裁剪提取：
    将图像按与嵌入相同的规则划分为4个象限，
    对每个象限独立进行一维循环解码和同步头搜索。
    收集所有象限的候选结果，通过出现频率表决得出最终水印。
"""

import cv2
import numpy as np
from collections import Counter
from .embed import (
    Watermarker,
    BLOCK_SIZE,
    POS1,
    POS2,
    SYNC_HEADER,
    REPEAT,
    _bits_to_text,
    _get_quadrants,
)


# ========== 工具函数 ==========

def _repeat_decode(bits: list, repeat: int = REPEAT) -> list:
    """重复解码：多数表决（3取2）"""
    decoded = []
    for i in range(0, len(bits) - repeat + 1, repeat):
        chunk = bits[i : i + repeat]
        decoded.append(1 if sum(chunk) > repeat // 2 else 0)
    return decoded


def _calc_confidence(raw_bits: list, repeat: int = REPEAT) -> float:
    """计算提取置信度"""
    if len(raw_bits) < repeat:
        return 0.0
    agreements = 0
    total = 0
    for i in range(0, len(raw_bits) - repeat + 1, repeat):
        chunk = raw_bits[i : i + repeat]
        majority = 1 if sum(chunk) > repeat // 2 else 0
        agreements += sum(1 for b in chunk if b == majority)
        total += len(chunk)
    return (agreements / total) * 100.0 if total > 0 else 0.0


def _extract_from_region(y_channel: np.ndarray, y0: int, y1: int,
                         x0: int, x1: int, sync_header: list) -> list:
    """
    从指定区域提取候选水印列表
    :return: [(watermark_text, confidence), ...]
    """
    region_h = y1 - y0
    region_w = x1 - x0
    num_blocks_h = region_h // BLOCK_SIZE
    num_blocks_w = region_w // BLOCK_SIZE
    p1, p2 = POS1, POS2
    raw_bits = []

    for i in range(num_blocks_h):
        for j in range(num_blocks_w):
            by0 = y0 + i * BLOCK_SIZE
            by1 = by0 + BLOCK_SIZE
            bx0 = x0 + j * BLOCK_SIZE
            bx1 = bx0 + BLOCK_SIZE

            block = y_channel[by0:by1, bx0:bx1]
            if block.shape[0] != BLOCK_SIZE or block.shape[1] != BLOCK_SIZE:
                continue
            dct_block = cv2.dct(block)
            bit = 1 if dct_block[p1] > dct_block[p2] else 0
            raw_bits.append(bit)

    if len(raw_bits) < len(sync_header) * REPEAT + 16 * REPEAT + 8:
        return []

    decoded_bits = _repeat_decode(raw_bits, REPEAT)
    confidence = _calc_confidence(raw_bits, REPEAT)

    header_len = len(sync_header)
    min_need = header_len + 16 + 1
    candidates = []

    for i in range(len(decoded_bits) - min_need + 1):
        if decoded_bits[i : i + header_len] == sync_header:
            start = i + header_len
            length_bits = decoded_bits[start : start + 16]
            wm_len = 0
            for bit in length_bits:
                wm_len = (wm_len << 1) | bit

            if 0 < wm_len <= 65535:
                wm_start = start + 16
                wm_end = wm_start + wm_len
                if wm_end <= len(decoded_bits):
                    wm_bits = decoded_bits[wm_start:wm_end]
                    wm_text = _bits_to_text(wm_bits)
                    if wm_text and any(c.isprintable() for c in wm_text):
                        candidates.append((wm_text, confidence))

    return candidates


# ========== 核心类 ==========

class WatermarkerExtractor(Watermarker):
    """DCT水印提取器"""

    def extract(self, image_path: str) -> dict:
        """从图像中提取水印（4象限独立提取 + 多副本表决）"""
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {"success": False, "error": f"无法读取图像: {image_path}"}

            ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
            y_channel = ycrcb[:, :, 0].astype(np.float32)
            h, w = y_channel.shape

            quadrants = _get_quadrants(h, w)
            all_candidates = []
            valid_regions = 0

            for idx, (y0, y1, x0, x1) in enumerate(quadrants):
                cands = _extract_from_region(y_channel, y0, y1, x0, x1, self.sync_header)
                if cands:
                    valid_regions += 1
                    all_candidates.extend(cands)

            if not all_candidates:
                # 所有象限都未找到，尝试全局提取（兼容旧方案或极端裁剪）
                cands = _extract_from_region(y_channel, 0, h, 0, w, self.sync_header)
                if cands:
                    all_candidates.extend(cands)
                    valid_regions = 1

            if not all_candidates:
                return {
                    "success": False,
                    "error": "未找到有效水印数据。图像可能未嵌入水印，或经历了严重破坏。",
                }

            # 多副本表决：统计各文本出现次数，取最频繁的
            texts = [c[0] for c in all_candidates]
            most_common = Counter(texts).most_common(1)[0]
            best_text, count = most_common

            # 计算平均置信度
            avg_conf = sum(c[1] for c in all_candidates if c[0] == best_text) / count

            return {
                "success": True,
                "watermark": best_text,
                "confidence": round(float(avg_conf), 2),
                "sync_found": True,
                "regions_valid": valid_regions,
                "regions_total": len(quadrants),
                "copies_found": len(all_candidates),
                "best_copy_count": count,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


# ========== 模块统一接口 ==========

def extract_watermark(image_path: str, **kwargs) -> dict:
    """提取水印"""
    extractor = WatermarkerExtractor(alpha=kwargs.get("alpha", 0.18))
    return extractor.extract(image_path)