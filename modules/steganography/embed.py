"""steganography/embed.py —— 水印嵌入模块

基于DCT频域的鲁棒数字水印（周期性循环嵌入方案）

抗裁剪机制：
    将 [同步头+长度+水印数据] 构成的数据帧进行(3,1)重复编码后，
    周期性循环嵌入到图像的每一个8x8 DCT块中。
    即使图像被裁剪，剩余块中仍包含完整的数据帧副本，
    提取时通过滑动窗口搜索同步头即可恢复。
"""

import cv2
import numpy as np
import os

# ========== 常量配置 ==========
BLOCK_SIZE = 8
POS1 = (2, 3)   # 中频系数位置1
POS2 = (3, 2)   # 中频系数位置2
SYNC_HEADER = [1, 0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0]  # 16bit同步头
REPEAT = 3      # (3,1)重复编码


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
    # 移除末尾零填充
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
    """计算PSNR（峰值信噪比）"""
    mse = np.mean((original.astype(np.float64) - processed.astype(np.float64)) ** 2)
    if mse == 0:
        return float("inf")
    return 10 * np.log10((255.0 ** 2) / mse)


def _qim_modify(dct_block: np.ndarray, bit: int, alpha: float) -> np.ndarray:
    """
    QIM（量化索引调制）核心逻辑
    通过保持/反转两个中频系数的相对大小关系来编码 0/1
    """
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
        """
        构建完整数据帧
        :return: (重复编码后的bit列表, 原始水印bit长度)
        """
        watermark_bits = _text_to_bits(watermark_text)
        length = len(watermark_bits)
        if length > 65535:
            raise ValueError("水印文本过长（最大支持65535 bit，约8KB）")

        length_bits = [(length >> i) & 1 for i in range(15, -1, -1)]
        data_bits = self.sync_header + length_bits + watermark_bits
        frame_bits = _repeat_encode(data_bits, REPEAT)
        return frame_bits, length

    def embed(self, image_path: str, watermark_text: str, output_path: str) -> dict:
        """
        嵌入水印到图像

        数据帧周期性循环嵌入所有DCT块，天然抗裁剪。
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {"success": False, "error": f"无法读取图像: {image_path}"}
            original = img.copy()

            # YCrCb色彩空间，仅处理Y通道（亮度）
            ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
            y_channel = ycrcb[:, :, 0].astype(np.float32)

            h, w = y_channel.shape
            num_blocks_h = h // self.block_size
            num_blocks_w = w // self.block_size
            total_blocks = num_blocks_h * num_blocks_w

            # 构建数据帧
            try:
                frame_bits, wm_len = self._build_frame(watermark_text)
            except ValueError as e:
                return {"success": False, "error": str(e)}

            frame_len = len(frame_bits)
            if total_blocks < frame_len:
                min_size = self.block_size * int(np.ceil(np.sqrt(frame_len)))
                return {
                    "success": False,
                    "error": (
                        f"图像容量不足。需要{frame_len}个DCT块，当前仅有{total_blocks}个块。"
                        f"建议图像尺寸至少为 {min_size}x{min_size} 像素。"
                    ),
                }

            # 周期性嵌入：每个块嵌入 frame_bits[block_idx % frame_len]
            y_modified = y_channel.copy()
            alpha = self.alpha

            for i in range(num_blocks_h):
                for j in range(num_blocks_w):
                    block_idx = i * num_blocks_w + j
                    bit = frame_bits[block_idx % frame_len]

                    y0 = i * self.block_size
                    y1 = (i + 1) * self.block_size
                    x0 = j * self.block_size
                    x1 = (j + 1) * self.block_size

                    block = y_modified[y0:y1, x0:x1]
                    dct_block = cv2.dct(block)
                    dct_block = _qim_modify(dct_block, bit, alpha)
                    y_modified[y0:y1, x0:x1] = cv2.idct(dct_block)

            # 合并回图像
            ycrcb[:, :, 0] = np.clip(y_modified, 0, 255).astype(np.uint8)
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
                "total_blocks": total_blocks,
                "repeat_times": total_blocks // frame_len,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


# ========== 模块统一接口 ==========

def embed_watermark(image_path: str, watermark_text: str, output_path: str, **kwargs) -> dict:
    """
    嵌入水印

    :param image_path: 原始图像路径（OpenCV支持的格式）
    :param watermark_text: 要嵌入的水印文本
    :param output_path: 输出图像路径（建议.png以无损保存水印）
    :param kwargs: alpha - 水印强度，默认0.18（范围0.1~0.3）
    :return: {"success": bool, "output_path": str, "psnr": float, ...}
    """
    watermarker = Watermarker(alpha=kwargs.get("alpha", 0.18))
    return watermarker.embed(image_path, watermark_text, output_path)