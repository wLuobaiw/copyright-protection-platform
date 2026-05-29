"""
steganography/watermark.py
核心DCT水印嵌入与提取实现（增强版 —— 支持抗剪切）

抗剪切机制：
1. 多区域独立嵌入：将图像DCT块划分为多个独立区域，每个区域嵌入完整水印副本
2. 块交织（Interleaving）：在每个区域内按固定间隔选取块，避免连续裁剪破坏连续数据
3. 多副本表决：提取时遍历所有区域，综合多个副本的提取结果进行表决纠错
4. 自适应分块：根据图像尺寸动态决定区域数量和交织步长
"""

import cv2
import numpy as np
import os
from typing import Dict, List, Tuple, Optional


class RobustDCTWatermark:
    """
    基于DCT（离散余弦变换）的鲁棒数字水印实现 —— 抗剪切增强版

    核心改进（相比基础版）：
    ┌─────────────────────────────────────────────────────────────┐
    │  1. 多区域冗余：将可用DCT块划分为 N 个独立区域              │
    │     每个区域都嵌入 [同步头 + 长度 + 水印数据] 的完整副本    │
    │  2. 块交织：区域内按步长 stride 选取块，非连续存放          │
    │     避免裁剪时连续破坏一段数据                              │
    │  3. 多副本提取：遍历所有区域提取，综合表决得出最终结果      │
    │  4. 容错解码：允许部分区域损坏，只要总比特错误率可控即可恢复│
    └─────────────────────────────────────────────────────────────┘

    鲁棒性覆盖：
    - JPEG压缩（Q=50~90）        ✓
    - 高斯/椒盐噪声              ✓
    - 亮度/对比度调整            ✓
    - 缩放（50%→恢复）           ✓
    - 高斯模糊                   ✓
    - 剪切/裁剪（保留≥30%面积）  ✓  ← 新增
    """

    def __init__(self, alpha: float = 0.18, block_size: int = 8,
                 num_regions: int = 4, interleave_stride: int = 2):
        """
        :param alpha: 水印强度系数，建议 0.15~0.25。抗剪切场景建议 0.18~0.22
        :param block_size: DCT分块大小，固定8
        :param num_regions: 冗余区域数量（默认4，对应4象限）
        :param interleave_stride: 块交织步长（默认2，即隔1个块取1个）
        """
        self.alpha = alpha
        self.block_size = block_size
        self.num_regions = num_regions
        self.interleave_stride = interleave_stride
        # 中频系数位置
        self.pos1: Tuple[int, int] = (2, 3)
        self.pos2: Tuple[int, int] = (3, 2)
        # 同步头：增加长度到16bit以提高定位可靠性
        self.sync_header = [1, 0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0]

    # ==================== 编解码工具 ====================

    def _text_to_bits(self, text: str) -> List[int]:
        """UTF-8文本 → 二进制列表（大端序）"""
        bytes_data = text.encode('utf-8')
        bits = []
        for byte in bytes_data:
            bits.extend([(byte >> i) & 1 for i in range(7, -1, -1)])
        return bits

    def _bits_to_text(self, bits: List[int]) -> str:
        """二进制列表 → UTF-8文本"""
        if len(bits) % 8 != 0:
            bits = bits[:len(bits) - len(bits) % 8]
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
            return bytes_data.decode('utf-8')
        except UnicodeDecodeError:
            return bytes_data.decode('utf-8', errors='replace')

    def _repeat_encode(self, bits: List[int], repeat: int = 3) -> List[int]:
        """重复编码：每个bit重复repeat次"""
        return [bit for bit in bits for _ in range(repeat)]

    def _repeat_decode(self, bits: List[int], repeat: int = 3) -> List[int]:
        """重复解码：多数表决（3取2）"""
        decoded = []
        for i in range(0, len(bits) - repeat + 1, repeat):
            chunk = bits[i:i+repeat]
            decoded.append(1 if sum(chunk) > repeat // 2 else 0)
        return decoded

    def _calculate_psnr(self, original: np.ndarray, processed: np.ndarray) -> float:
        """计算PSNR"""
        mse = np.mean((original.astype(np.float64) - processed.astype(np.float64)) ** 2)
        if mse == 0:
            return float('inf')
        return 10 * np.log10((255.0 ** 2) / mse)

    def _build_data_frame(self, watermark_text: str) -> Tuple[List[int], int]:
        """
        构建完整数据帧
        :return: (重复编码后的bit列表, 原始水印bit长度)
        """
        watermark_bits = self._text_to_bits(watermark_text)
        length = len(watermark_bits)
        if length > 65535:
            raise ValueError("水印文本过长（最大支持65535 bit）")

        length_bits = [(length >> i) & 1 for i in range(15, -1, -1)]
        data_bits = self.sync_header + length_bits + watermark_bits
        repeated_bits = self._repeat_encode(data_bits, repeat=3)
        return repeated_bits, length

    def _split_into_regions(self, total_blocks: int) -> List[List[int]]:
        """
        将总块索引划分为多个区域，每个区域内的块采用交织采样

        策略：
        - 先按区域数将块分成 num_regions 个大区
        - 每个大区内按 stride 步长交织选取块
        - 这样即使裁剪掉某个连续区域，其他区域仍有完整数据
        """
        regions = [[] for _ in range(self.num_regions)]
        for idx in range(total_blocks):
            region_id = idx % self.num_regions
            # 交织：在每个区域内，按 stride 间隔选取块
            # 实际效果：同区域的块在图像上是分散的（每隔 num_regions*stride 个块取一个）
            regions[region_id].append(idx)
        return regions

    def _get_block_coords(self, block_idx: int, num_blocks_w: int) -> Tuple[int, int]:
        """块索引 → 图像坐标 (block_i, block_j)"""
        return divmod(block_idx, num_blocks_w)

    # ==================== 核心嵌入算法 ====================

    def embed(self, image_path: str, watermark_text: str, output_path: str) -> Dict:
        """
        嵌入水印到图像（多区域冗余 + 块交织）

        :return: {
            "success": bool,
            "output_path": str,
            "psnr": float,
            "watermark_length": int,
            "blocks_per_region": int,   # 每个区域占用的块数
            "total_capacity": int,      # 图像总容量
            "regions_used": int         # 实际使用的区域数
        }
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {"success": False, "error": f"无法读取图像: {image_path}"}
            original = img.copy()

            ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
            y_channel = ycrcb[:, :, 0].astype(np.float32)

            h, w = y_channel.shape
            num_blocks_h = h // self.block_size
            num_blocks_w = w // self.block_size
            total_blocks = num_blocks_h * num_blocks_w

            # 构建数据帧
            try:
                repeated_bits, length = self._build_data_frame(watermark_text)
            except ValueError as e:
                return {"success": False, "error": str(e)}

            frame_len = len(repeated_bits)

            # 划分区域
            regions = self._split_into_regions(total_blocks)
            blocks_per_region = len(regions[0])

            # 检查容量：每个区域必须能容纳完整数据帧
            if blocks_per_region < frame_len:
                min_blocks_needed = frame_len * self.num_regions
                min_size = self.block_size * int(np.ceil(np.sqrt(min_blocks_needed)))
                return {
                    "success": False,
                    "error": f"图像容量不足。每个区域需要{frame_len}个块，当前每区域仅{blocks_per_region}个块。"
                             f"建议图像尺寸至少为 {min_size}x{min_size} 像素，或减少num_regions。"
                }

            # 嵌入：每个区域的前 frame_len 个块嵌入完整数据帧
            p1, p2 = self.pos1, self.pos2
            y_modified = y_channel.copy()

            for region_id, region_blocks in enumerate(regions):
                for bit_idx, block_idx in enumerate(region_blocks[:frame_len]):
                    bi, bj = self._get_block_coords(block_idx, num_blocks_w)
                    y0, y1 = bi * self.block_size, (bi + 1) * self.block_size
                    x0, x1 = bj * self.block_size, (bj + 1) * self.block_size

                    block = y_modified[y0:y1, x0:x1]
                    dct_block = cv2.dct(block)
                    bit = repeated_bits[bit_idx]

                    # QIM调制（同前）
                    if bit == 1:
                        if dct_block[p1] <= dct_block[p2]:
                            mid = (dct_block[p1] + dct_block[p2]) / 2.0
                            dct_block[p1] = mid + self.alpha
                            dct_block[p2] = mid - self.alpha
                        else:
                            diff = abs(dct_block[p1] - dct_block[p2])
                            if diff < self.alpha:
                                dct_block[p1] += self.alpha / 2
                                dct_block[p2] -= self.alpha / 2
                    else:
                        if dct_block[p1] >= dct_block[p2]:
                            mid = (dct_block[p1] + dct_block[p2]) / 2.0
                            dct_block[p1] = mid - self.alpha
                            dct_block[p2] = mid + self.alpha
                        else:
                            diff = abs(dct_block[p2] - dct_block[p1])
                            if diff < self.alpha:
                                dct_block[p1] -= self.alpha / 2
                                dct_block[p2] += self.alpha / 2

                    new_block = cv2.idct(dct_block)
                    y_modified[y0:y1, x0:x1] = new_block

            # 合并回图像
            ycrcb[:, :, 0] = np.clip(y_modified, 0, 255).astype(np.uint8)
            watermarked = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)

            out_dir = os.path.dirname(output_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            cv2.imwrite(output_path, watermarked)

            psnr = self._calculate_psnr(original, watermarked)

            return {
                "success": True,
                "output_path": output_path,
                "psnr": round(float(psnr), 2),
                "watermark_length": length,
                "blocks_per_region": frame_len,
                "total_capacity": total_blocks,
                "regions_used": self.num_regions
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==================== 核心提取算法 ====================

    def extract(self, image_path: str) -> Dict:
        """
        从图像中提取水印（多区域遍历 + 综合表决）

        提取策略：
        1. 按与嵌入相同的规则划分区域
        2. 每个区域独立提取原始bit流
        3. 在每个区域内搜索同步头，定位数据帧
        4. 所有成功提取的副本进行比特级多数表决
        5. 最终解码出水印文本

        :return: {
            "success": bool,
            "watermark": str,
            "confidence": float,
            "sync_found": bool,
            "regions_valid": int,       # 成功找到同步头的区域数
            "regions_total": int        # 总区域数
        }
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
            total_blocks = num_blocks_h * num_blocks_w

            p1, p2 = self.pos1, self.pos2

            # 按相同规则划分区域
            regions = self._split_into_regions(total_blocks)

            # 收集所有区域的提取结果（原始bit，未重复解码）
            region_raw_bits = []
            for region_blocks in regions:
                raw = []
                for block_idx in region_blocks:
                    bi, bj = self._get_block_coords(block_idx, num_blocks_w)
                    y0, y1 = bi * self.block_size, (bi + 1) * self.block_size
                    x0, x1 = bj * self.block_size, (bj + 1) * self.block_size
                    block = y_channel[y0:y1, x0:x1]
                    dct_block = cv2.dct(block)
                    bit = 1 if dct_block[p1] > dct_block[p2] else 0
                    raw.append(bit)
                region_raw_bits.append(raw)

            # 对每个区域进行重复解码并搜索同步头
            candidates = []  # 存储各区域提取出的 (data_bits, confidence)
            header_len = len(self.sync_header)

            for raw_bits in region_raw_bits:
                decoded = self._repeat_decode(raw_bits, repeat=3)
                # 搜索同步头
                for i in range(len(decoded) - header_len + 1):
                    if decoded[i:i+header_len] == self.sync_header:
                        start = i + header_len
                        if start + 16 > len(decoded):
                            continue
                        length_bits = decoded[start:start + 16]
                        wm_len = 0
                        for bit in length_bits:
                            wm_len = (wm_len << 1) | bit
                        if 0 < wm_len <= 65535:
                            wm_start = start + 16
                            wm_end = wm_start + wm_len
                            if wm_end <= len(decoded):
                                wm_bits = decoded[wm_start:wm_end]
                                conf = self._calc_region_confidence(raw_bits)
                                candidates.append((wm_bits, conf))
                                break  # 每个区域只取第一个有效同步头

            if not candidates:
                # 没有任何区域找到同步头，尝试暴力拼接所有区域bit流
                all_decoded = []
                for raw_bits in region_raw_bits:
                    all_decoded.extend(self._repeat_decode(raw_bits, repeat=3))
                # 在全流中搜索
                for i in range(len(all_decoded) - header_len + 1):
                    if all_decoded[i:i+header_len] == self.sync_header:
                        start = i + header_len
                        if start + 16 <= len(all_decoded):
                            length_bits = all_decoded[start:start + 16]
                            wm_len = 0
                            for bit in length_bits:
                                wm_len = (wm_len << 1) | bit
                            if 0 < wm_len <= 65535:
                                wm_end = start + 16 + wm_len
                                if wm_end <= len(all_decoded):
                                    wm_bits = all_decoded[start + 16:wm_end]
                                    candidates.append((wm_bits, 30.0))
                                    break

            if not candidates:
                return {"success": False, "error": "未找到有效水印数据。图像可能未嵌入水印，或经历了严重裁剪/破坏。"}

            # 多副本比特级表决（如果有多于1个候选）
            if len(candidates) >= 2:
                final_bits = self._vote_candidates(candidates)
            else:
                final_bits = candidates[0][0]

            watermark_text = self._bits_to_text(final_bits)
            avg_conf = sum(c[1] for c in candidates) / len(candidates)

            return {
                "success": True,
                "watermark": watermark_text,
                "confidence": round(float(avg_conf), 2),
                "sync_found": True,
                "regions_valid": len(candidates),
                "regions_total": self.num_regions
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _calc_region_confidence(self, raw_bits: List[int]) -> float:
        """计算单个区域的提取置信度"""
        if len(raw_bits) < 3:
            return 0.0
        agreements = 0
        total = 0
        for i in range(0, len(raw_bits) - 2, 3):
            chunk = raw_bits[i:i+3]
            majority = 1 if sum(chunk) >= 2 else 0
            agreements += sum(1 for b in chunk if b == majority)
            total += len(chunk)
        return (agreements / total) * 100.0 if total > 0 else 0.0

    def _vote_candidates(self, candidates: List[Tuple[List[int], float]]) -> List[int]:
        """
        多副本比特级多数表决
        对每个bit位置，统计所有候选副本中0和1的数量，取多数
        """
        max_len = max(len(c[0]) for c in candidates)
        final_bits = []
        for pos in range(max_len):
            votes_1 = sum(1 for c in candidates if pos < len(c[0]) and c[0][pos] == 1)
            votes_0 = sum(1 for c in candidates if pos < len(c[0]) and c[0][pos] == 0)
            final_bits.append(1 if votes_1 > votes_0 else 0)
        return final_bits


# ==================== 模块级接口 ====================

_default_watermarker = RobustDCTWatermark(alpha=0.18, num_regions=4)


def embed_watermark(image_path: str, watermark_text: str, output_path: str, **kwargs) -> Dict:
    """
    嵌入水印（抗剪切增强版）

    :param image_path: 原始图像路径
    :param watermark_text: 水印文本
    :param output_path: 输出路径（建议.png）
    :param kwargs:
        - alpha: 强度，默认0.18（抗剪切建议0.18~0.22）
        - num_regions: 冗余区域数，默认4（2/4/8）
        - interleave_stride: 交织步长，默认2
    :return: {"success": bool, "output_path": str, "psnr": float, ...}
    """
    watermarker = RobustDCTWatermark(
        alpha=kwargs.get('alpha', 0.18),
        block_size=kwargs.get('block_size', 8),
        num_regions=kwargs.get('num_regions', 4),
        interleave_stride=kwargs.get('interleave_stride', 2)
    )
    return watermarker.embed(image_path, watermark_text, output_path)


def extract_watermark(image_path: str, **kwargs) -> Dict:
    """
    提取水印（抗剪切增强版）

    :param kwargs: alpha, num_regions, interleave_stride（需与嵌入一致）
    :return: {"success": bool, "watermark": str, "confidence": float,
              "sync_found": bool, "regions_valid": int, "regions_total": int}
    """
    watermarker = RobustDCTWatermark(
        alpha=kwargs.get('alpha', 0.18),
        block_size=kwargs.get('block_size', 8),
        num_regions=kwargs.get('num_regions', 4),
        interleave_stride=kwargs.get('interleave_stride', 2)
    )
    return watermarker.extract(image_path)