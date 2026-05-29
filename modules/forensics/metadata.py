"""
元信息生成模块 - C 负责实现

生成证据包的 metadata.json，记录取证的上下文信息。
"""

import time


def create_metadata_json(
    source_url: str = "",
    capture_time: str = "",
    publisher: str = "",
    notes: str = "",
    officer: str = "取证员",
) -> dict:
    """
    生成取证元信息字典。

    参数说明：
        source_url:   侵权内容所在URL
        capture_time: 截图/取证时间
        publisher:    侵权发布者ID
        notes:        补充说明
        officer:      取证人员姓名
    """
    return {
        "source_url": source_url,
        "capture_time": capture_time,
        "publisher": publisher,
        "notes": notes,
        "forensics_officer": officer,
        "collection_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
