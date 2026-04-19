"""TaskProcessor utilities."""

from __future__ import annotations

_RETRY_DELAYS = [60, 300, 600, 1800, 3600]


def calculate_retry_delay(retry_count: int) -> int:
    """計算重試 delay（秒）。

    Args:
        retry_count: 當前重試次數（從 1 開始）。

    Returns:
        Delay 秒數：60/300/600/1800/3600。
    """
    if retry_count <= 0:
        return 0
    if retry_count <= len(_RETRY_DELAYS):
        return _RETRY_DELAYS[retry_count - 1]
    return _RETRY_DELAYS[-1]
