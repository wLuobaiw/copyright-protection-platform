"""steganography/extract.py —— 水印提取模块

基于DCT频域的盲水印提取（滑动窗口搜索方案）

抗裁剪提取：
    读取所有可用DCT块的bit，在bit流中滑动搜索同步头。
    由于数据帧是周期性循环嵌入的，即使图像被裁剪，
    剩余块中仍包含完整的 [同步头+长度+数据] 序列。
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
    """计算提取置信度：统计重复编码的表决一致率"""
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


# ========== 核心类 ==========

class WatermarkerExtractor(Watermarker):
    """DCT水印提取器（继承嵌入器以共享配置）"""

    def extract(self, image_path: str) -> dict:
        """
        从图像中提取水印

        滑动窗口搜索同步头，支持裁剪后提取。
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {"success": False, "error": f"无法读取图像: {image_path}"}

            ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
            y_channel = ycrcb[:, :, 0].astype(np.float32)

            h, w = y_channel.shape
            num_blocks_h = h // self.block_size
            num_blocks_w = w // self.block_size

            p1, p2 = self.pos1, self.pos2
            raw_bits = []

            # 从每个DCT块提取1bit（基于中频系数对相对大小）
            for i in range(num_blocks_h):
                for j in range(num_blocks_w):
                    y0 = i * self.block_size
                    y1 = (i + 1) * self.block_size
                    x0 = j * self.block_size
                    x1 = (j + 1) * self.block_size

                    block = y_channel[y0:y1, x0:x1]
                    dct_block = cv2.dct(block)
                    bit = 1 if dct_block[p1] > dct_block[p2] else 0
                    raw_bits.append(bit)

            # 重复解码（3取2多数表决）
            decoded_bits = _repeat_decode(raw_bits, REPEAT)
            confidence = _calc_confidence(raw_bits, REPEAT)

            # 滑动窗口搜索同步头
            header_len = len(self.sync_header)
            candidates = []  # (watermark_text, start_index)

            # 最小需要的长度：同步头 + 16bit长度 + 至少1bit数据
            min_need = header_len + 16 + 1
            for i in range(len(decoded_bits) - min_need + 1):
                if decoded_bits[i : i + header_len] == self.sync_header:
                    # 找到同步头，解析16bit长度
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
                            # 过滤空结果和纯乱码
                            if wm_text and any(c.isprintable() for c in wm_text):
                                candidates.append((wm_text, i))

            if not candidates:
                return {
                    "success": False,
                    "error": "未找到有效水印数据。图像可能未嵌入水印，或经历了严重破坏。",
                    "confidence": round(float(confidence), 2),
                }

            # 多副本去重：统计各文本出现次数，取最频繁的
            texts = [c[0] for c in candidates]
            most_common = Counter(texts).most_common(1)[0]
            best_text, count = most_common

            return {
                "success": True,
                "watermark": best_text,
                "confidence": round(float(confidence), 2),
                "sync_found": True,
                "copies_found": len(candidates),
                "best_copy_count": count,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


# ========== 模块统一接口 ==========

def extract_watermark(image_path: str, **kwargs) -> dict:
    """
    提取水印

    :param image_path: 含水印图像路径
    :param kwargs: alpha - 水印强度（需与嵌入时一致），默认0.18
    :return: {"success": bool, "watermark": str, "confidence": float, ...}
    """
    extractor = WatermarkerExtractor(alpha=kwargs.get("alpha", 0.18))
    return extractor.extract(image_path)