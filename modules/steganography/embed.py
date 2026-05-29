"""steganography/embed.py —— 水印嵌入模块

基于DCT频域的鲁棒数字水印（智能象限/全局混合嵌入）

嵌入策略：
    1. 计算数据帧长度
    2. 如果每象限容量 >= 帧长度 → 4象限独立嵌入（抗剪切）
    3. 否则 → 全局一维循环嵌入（容量充足，抗上下裁剪）

关键修复（解决"guixiang→guixianf"问题）：
    - alpha=5.0：确保经uint8量化后DCT系数关系仍稳定
    - 强制差异>=alpha：无论原始系数如何，都确保目标关系
    - np.round()代替astype()：四舍五入比截断更公平
    - 16bit同步头：降低假匹配概率
"""

import cv2
import numpy as np
import os


def _imread(path: str):
    """cv2.imread 在 Windows 上不支持中文路径，用 imdecode 绕过"""
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _imwrite(path: str, img: np.ndarray) -> bool:
    """cv2.imwrite 在 Windows 上不支持中文路径，用 imencode + tofile 绕过"""
    ext = os.path.splitext(path)[1]
    success, buf = cv2.imencode(ext, img)
    if success:
        buf.tofile(path)
    return success

BLOCK_SIZE = 8
POS1 = (2, 3)
POS2 = (3, 2)
SYNC_HEADER = [1, 0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0]  # 16bit
REPEAT = 3
DEFAULT_ALPHA = 5.0  # 大幅提高，确保uint8量化后信号稳定


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
    强化QIM：无条件确保系数关系正确，且差异 >= alpha。
    解决原方案"关系正确但不修改"导致信号丢失的问题。
    """
    p1, p2 = POS1, POS2
    c1, c2 = float(dct_block[p1]), float(dct_block[p2])

    if bit == 1:
        # 必须 c1 > c2，且差异 >= alpha
        if c1 <= c2 or (c1 - c2) < alpha:
            mid = (c1 + c2) / 2.0
            dct_block[p1] = mid + alpha / 2.0
            dct_block[p2] = mid - alpha / 2.0
    else:
        # 必须 c2 > c1，即 c1 - c2 <= -alpha
        if c2 <= c1 or (c2 - c1) < alpha:
            mid = (c1 + c2) / 2.0
            dct_block[p1] = mid - alpha / 2.0
            dct_block[p2] = mid + alpha / 2.0

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
            img = _imread(image_path)
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

            # 检查每象限容量
            min_quad_blocks = float("inf")
            for y0, y1, x0, x1 in quadrants:
                bh = (y1 - y0) // self.block_size
                bw = (x1 - x0) // self.block_size
                total = bh * bw
                if total < min_quad_blocks:
                    min_quad_blocks = total

            use_quadrants = min_quad_blocks >= frame_len

            if use_quadrants:
                # 4象限独立嵌入
                for y0, y1, x0, x1 in quadrants:
                    self._embed_in_region(y_channel, frame_bits, y0, y1, x0, x1)
                mode = "quadrant"
            else:
                # 全局一维循环嵌入（容量充足）
                self._embed_in_region(y_channel, frame_bits, 0, h, 0, w)
                mode = "global"

            # 关键修复：四舍五入代替截断
            ycrcb[:, :, 0] = np.clip(np.round(y_channel), 0, 255).astype(np.uint8)
            watermarked = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)

            out_dir = os.path.dirname(output_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            _imwrite(output_path, watermarked)

            psnr = _calculate_psnr(original, watermarked)

            return {
                "success": True,
                "output_path": output_path,
                "psnr": round(float(psnr), 2),
                "watermark_length": wm_len,
                "frame_length": frame_len,
                "embed_mode": mode,
                "quadrant_capacity": min_quad_blocks if use_quadrants else 0,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


def embed_watermark(image_path: str, watermark_text: str, output_path: str, **kwargs) -> dict:
    watermarker = Watermarker(alpha=kwargs.get("alpha", DEFAULT_ALPHA))
    return watermarker.embed(image_path, watermark_text, output_path)