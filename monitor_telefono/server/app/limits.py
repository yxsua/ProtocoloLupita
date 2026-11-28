from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque


class FailureLockout:
    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: int = 15 * 60,
        lock_seconds: int = 15 * 60,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.lock_seconds = lock_seconds
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            locked_until = self._locked_until.get(key, 0)
            if locked_until > now:
                return max(1, int(locked_until - now + 0.999))
            self._locked_until.pop(key, None)
            failures = self._failures.get(key)
            if failures is None:
                return 0
            while failures and now - failures[0] >= self.window_seconds:
                failures.popleft()
            if not failures:
                self._failures.pop(key, None)
            return 0

    def record_failure(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            locked_until = self._locked_until.get(key, 0)
            if locked_until > now:
                return max(1, int(locked_until - now + 0.999))
            failures = self._failures.setdefault(key, deque())
            self._failures.move_to_end(key)
            while len(self._failures) > 10000:
                expired_key, _ = self._failures.popitem(last=False)
                self._locked_until.pop(expired_key, None)
            while failures and now - failures[0] >= self.window_seconds:
                failures.popleft()
            failures.append(now)
            if len(failures) >= self.max_failures:
                self._locked_until[key] = now + self.lock_seconds
                failures.clear()
                return self.lock_seconds
            return 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)
