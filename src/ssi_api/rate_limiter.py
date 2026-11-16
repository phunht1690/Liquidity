"""Bộ giới hạn dự phòng cho REST chỉ đọc sau này; chưa gọi API nào."""

import threading
import time


class RateLimiter:
    """Giãn đều yêu cầu, tối đa 5 lần/giây cho một đối tượng dùng chung."""

    def __init__(self, requests_per_second: float = 5.0) -> None:
        if not 0 < requests_per_second <= 5:
            raise ValueError("Tần suất phải lớn hơn 0 và không quá 5 request/giây")
        self._interval = 1.0 / requests_per_second
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_allowed - now)
            if delay:
                time.sleep(delay)
            self._next_allowed = time.monotonic() + self._interval
