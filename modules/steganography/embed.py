"""steganography/embed.py —— 水印嵌入模块

基于DCT频域的鲁棒数字水印（4象限独立循环嵌入方案）

抗裁剪机制：
    将图像均分为4个象限（左上/右上/左下/右下），
    每个象限内部独立进行一维循环嵌入完整数据帧。
    提取时对每个象限独立解码，综合表决。

    边缘裁剪场景：
    - 顶部裁剪 → 左下、右下象限完整保留 → 可提取
    - 底部裁剪 → 左上、右上象限完整保留 → 可提取
    - 左侧裁剪 → 右上、右下象限完整保留 → 可提取
    - 右侧裁剪 → 左上、左下象限完整保留 → 可提取
    - 中心裁剪 → 4象限各保留部分，通过多副本容错提取
"""

import cv2
import numpy as np
import os

# ========== 常量配置 ==========
BLOCK_SIZE = 8
POS1 = (2, 3)
POS2 = (3, 2)
SYNC_HEADER = [1, 0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0]
REPEAT = 3
NUM_QUADRANTS = 4  # 2x2 象限划分


# ========== 工具函数 ==========

def _text_to_bits(text: str) -> list:
    """UTF-8文本 → 二进制列表（大端序）"""
    bytes_data = text.encode("utf-8")
    bits = []
    for byte in bytes_data:
        bits.extend([(byte >> i) & 1 for i in range(7, -1, -1)])
    return bits


def _bits_to_text(bits: list) -> str:
    """二进制列表 → UTF-8文本"""
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
    """重复编码：每个bit重复repeat次"""
    return [bit for bit in bits for _ in range(repeat)]


def _calculate_psnr(original: np.ndarray, processed: np.ndarray) -> float:
    """计算PSNR"""
    mse = np.mean((original.astype(np.float64) - processed.astype(np.float64)) ** 2)
    if mse == 0:
        return float("inf")
    return 10 * np.log10((255.0 ** 2) / mse)


def _qim_modify(dct_block: np.ndarray, bit: int, alpha: float) -> np.ndarray:
    """QIM量化索引调制"""
    p1, p2 = POS1, POS2
    if bit == 1:
        if dct_block[p1] <= dct_block[p2]:
            mid = (dct_block[p1] + dct_block[p2]) / 2.0
            dct_block[p1] = mid + alpha
            dct_block[p2] = mid - alpha
        else:
            diff = abs(dct_block[p1] - dct_block[p2])
            if diff < alpha:
                dct_block[p1] += alpha / 2
                dct_block[p2] -= alpha / 2
    else:
        if dct_block[p1] >= dct_block[p2]:
            mid = (dct_block[p1] + dct_block[p2]) / 2.0
            dct_block[p1] = mid - alpha
            dct_block[p2] = mid + alpha
        else:
            diff = abs(dct_block[p2] - dct_block[p1])
            if diff < alpha:
                dct_block[p1] -= alpha / 2
                dct_block[p2] += alpha / 2
    return dct_block


def _get_quadrants(h: int, w: int) -> list:
    """
    将图像划分为4个象限（像素坐标）
    返回: [(y0, y1, x0, x1), ...]
    """
    mid_h = h // 2
    mid_w = w // 2
    # 确保边界对齐到BLOCK_SIZE的倍数
    mid_h = (mid_h // BLOCK_SIZE) * BLOCK_SIZE
    mid_w = (mid_w // BLOCK_SIZE) * BLOCK_SIZE
    return [
        (0, mid_h, 0, mid_w),         # 左上
        (0, mid_h, mid_w, w),         # 右上
        (mid_h, h, 0, mid_w),         # 左下
        (mid_h, h, mid_w, w),         # 右下
    ]


# ========== 核心类 ==========

class Watermarker:
    """DCT水印嵌入器"""

    def __init__(self, alpha: float = 0.18):
        self.alpha = alpha
        self.block_size = BLOCK_SIZE
        self.pos1 = POS1
        self.pos2 = POS2
        self.sync_header = SYNC_HEADER

    def _build_frame(self, watermark_text: str) -> tuple:
        """构建完整数据帧"""
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
        """在指定区域内循环嵌入数据帧"""
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
        """嵌入水印到图像（4象限独立循环嵌入）"""
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {"success": False, "error": f"无法读取图像: {image_path}"}
            original = img.copy()

            ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
            y_channel = ycrcb[:, :, 0].astype(np.float32)
            h, w = y_channel.shape

            # 构建数据帧
            try:
                frame_bits, wm_len = self._build_frame(watermark_text)
            except ValueError as e:
                return {"success": False, "error": str(e)}

            frame_len = len(frame_bits)

            # 检查最小象限容量
            quadrants = _get_quadrants(h, w)
            min_blocks = float("inf")
            for y0, y1, x0, x1 in quadrants:
                bh = (y1 - y0) // self.block_size
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

            # 4象限独立嵌入
            for y0, y1, x0, x1 in quadrants:
                self._embed_in_region(y_channel, frame_bits, y0, y1, x0, x1)

            # 保存
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


# ========== 模块统一接口 ==========

def embed_watermark(image_path: str, watermark_text: str, output_path: str, **kwargs) -> dict:
    """嵌入水印"""
    watermarker = Watermarker(alpha=kwargs.get("alpha", 0.18))
    return watermarker.embed(image_path, watermark_text, output_path)