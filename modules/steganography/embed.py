"""steganography/embed.py —— 水印嵌入模块

基于DCT频域的鲁棒数字水印（4象限独立循环嵌入方案）

抗裁剪机制：
    将图像均分为4个象限，每个象限内部独立循环嵌入完整数据帧。
    提取时对每个象限独立解码，综合表决。
"""

import cv2
import numpy as np
import os

BLOCK_SIZE = 8
POS1 = (2, 3)
POS2 = (3, 2)
SYNC_HEADER = [1, 0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0]
REPEAT = 3
DEFAULT_ALPHA = 0.5  # 从0.18提高到0.5，确保经uint8量化后信号仍稳定


def _text_to_bits(text: str) -> list:
    bytes_data = text.encode("utf-8")
    bits = []
    for byte in bytes_data:
        bits.extend([(byte >> i) & 1 for i in range(7, -1, -1)])
    return bits


def _bits_to_text(bits: list) -> str:
    if len(bits) % 8 != 0:
        bits = bits[: len(bits) - len(bits) % 8]
    bytes_data = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        bytes_data.append(byte)
    while bytes_data and bytes_data[-1] == 0:
        bytes_data.pop()
    try:
        return bytes_data.decode("utf-8")
    except UnicodeDecodeError:
        return bytes_data.decode("utf-8", errors="replace")


def _repeat_encode(bits: list, repeat: int = REPEAT) -> list:
    return [bit for bit in bits for _ in range(repeat)]


def _calculate_psnr(original: np.ndarray, processed: np.ndarray) -> float:
    mse = np.mean((original.astype(np.float64) - processed.astype(np.float64)) ** 2)
    if mse == 0:
        return float("inf")
    return 10 * np.log10((255.0 ** 2) / mse)


def _qim_modify(dct_block: np.ndarray, bit: int, alpha: float) -> np.ndarray:
    """
    强化QIM：确保IDCT->uint8量化->DCT后，系数关系仍然稳定。
    关键改进：无论原始关系如何，都确保两个系数的差异 >= alpha。
    """
    p1, p2 = POS1, POS2
    c1, c2 = float(dct_block[p1]), float(dct_block[p2])

    # 计算当前差异
    diff = c1 - c2

    if bit == 1:
        # 需要 c1 > c2，且差异 >= alpha
        if diff < alpha:
            # 强制设置差异为 alpha * 1.5（留有余量对抗量化噪声）
            target_diff = alpha * 1.5
            mid = (c1 + c2) / 2.0
            dct_block[p1] = mid + target_diff / 2
            dct_block[p2] = mid - target_diff / 2
    else:
        # 需要 c2 > c1，即 c1 - c2 <= -alpha
        if diff > -alpha:
            target_diff = alpha * 1.5
            mid = (c1 + c2) / 2.0
            dct_block[p1] = mid - target_diff / 2
            dct_block[p2] = mid + target_diff / 2

    return dct_block


def _get_quadrants(h: int, w: int) -> list:
    mid_h = (h // 2 // BLOCK_SIZE) * BLOCK_SIZE
    mid_w = (w // 2 // BLOCK_SIZE) * BLOCK_SIZE
    return [
        (0, mid_h, 0, mid_w),
        (0, mid_h, mid_w, w),
        (mid_h, h, 0, mid_w),
        (mid_h, h, mid_w, w),
    ]


class Watermarker:
    def __init__(self, alpha: float = DEFAULT_ALPHA):
        self.alpha = alpha
        self.block_size = BLOCK_SIZE
        self.pos1 = POS1
        self.pos2 = POS2
        self.sync_header = SYNC_HEADER

    def _build_frame(self, watermark_text: str) -> tuple:
        watermark_bits = _text_to_bits(watermark_text)
        length = len(watermark_bits)
        if length > 65535:
            raise ValueError("水印文本过长（最大支持65535 bit，约8KB）")
        length_bits = [(length >> i) & 1 for i in range(15, -1, -1)]
        data_bits = self.sync_header + length_bits + watermark_bits
        frame_bits = _repeat_encode(data_bits, REPEAT)
        return frame_bits, length

    def _embed_in_region(self, y_channel: np.ndarray, frame_bits: list,
                         y0: int, y1: int, x0: int, x1: int) -> None:
        region_h = y1 - y0
        region_w = x1 - x0
        num_blocks_h = region_h // self.block_size
        num_blocks_w = region_w // self.block_size
        frame_len = len(frame_bits)
        alpha = self.alpha

        for i in range(num_blocks_h):
            for j in range(num_blocks_w):
                block_idx = i * num_blocks_w + j
                bit = frame_bits[block_idx % frame_len]

                by0 = y0 + i * self.block_size
                by1 = by0 + self.block_size
                bx0 = x0 + j * self.block_size
                bx1 = bx0 + self.block_size

                block = y_channel[by0:by1, bx0:bx1]
                if block.shape[0] != self.block_size or block.shape[1] != self.block_size:
                    continue
                dct_block = cv2.dct(block)
                dct_block = _qim_modify(dct_block, bit, alpha)
                y_channel[by0:by1, bx0:bx1] = cv2.idct(dct_block)

    def embed(self, image_path: str, watermark_text: str, output_path: str) -> dict:
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {"success": False, "error": f"无法读取图像: {image_path}"}
            original = img.copy()

            ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
            y_channel = ycrcb[:, :, 0].astype(np.float32)
            h, w = y_channel.shape

            try:
                frame_bits, wm_len = self._build_frame(watermark_text)
            except ValueError as e:
                return {"success": False, "error": str(e)}

            frame_len = len(frame_bits)
            quadrants = _get_quadrants(h, w)
            min_blocks = float("inf")
            for y0, y1, x0, x1 in quadrants:
                bh = (y1 - y0) // self.block_size
                bw = (x1 - x0) // self.block_size
                total = bh * bw
                if total < min_blocks:
                    min_blocks = total

            if min_blocks < frame_len:
                return {
                    "success": False,
                    "error": (
                        f"图像容量不足。最小象限仅有{min_blocks}个块，"
                        f"需要{frame_len}个块。建议图像尺寸至少 256x256 像素。"
                    ),
                }

            for y0, y1, x0, x1 in quadrants:
                self._embed_in_region(y_channel, frame_bits, y0, y1, x0, x1)

            ycrcb[:, :, 0] = np.clip(y_channel, 0, 255).astype(np.uint8)
            watermarked = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)

            out_dir = os.path.dirname(output_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            cv2.imwrite(output_path, watermarked)

            psnr = _calculate_psnr(original, watermarked)

            return {
                "success": True,
                "output_path": output_path,
                "psnr": round(float(psnr), 2),
                "watermark_length": wm_len,
                "frame_length": frame_len,
                "min_quadrant_blocks": min_blocks,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


def embed_watermark(image_path: str, watermark_text: str, output_path: str, **kwargs) -> dict:
    watermarker = Watermarker(alpha=kwargs.get("alpha", DEFAULT_ALPHA))
    return watermarker.embed(image_path, watermark_text, output_path)