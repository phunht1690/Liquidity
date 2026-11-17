"""Coalesce identical reads and bound concurrent, memory-heavy local queries."""
from collections import OrderedDict
from threading import BoundedSemaphore, Event, Lock
import time


class QueryBusy(RuntimeError):
    pass


class QueryCache:
    def __init__(self, *, max_entries=6, max_workers=2, ttl=2, wait_seconds=8, clock=time.monotonic):
        self.max_entries = max_entries
        self.ttl = ttl
        self.wait_seconds = wait_seconds
        self.clock = clock
        self._lock = Lock()
        self._slots = BoundedSemaphore(max_workers)
        self._ready = OrderedDict()
        self._inflight = {}

    def get(self, key, produce):
        with self._lock:
            entry = self._ready.get(key)
            if entry is not None and self.clock() - entry[0] < self.ttl:
                self._ready.move_to_end(key)
                return entry[1]
            event = self._inflight.get(key)
            owner = event is None
            if owner:
                if not self._slots.acquire(blocking=False):
                    raise QueryBusy('local_query_busy')
                event = Event()
                self._inflight[key] = event
        if not owner:
            if not event.wait(self.wait_seconds):
                raise QueryBusy('local_query_busy')
            with self._lock:
                entry = self._ready.get(key)
                if entry is not None and self.clock() - entry[0] < self.ttl:
                    return entry[1]
            raise QueryBusy('local_query_retry')
        try:
            value = produce()
            with self._lock:
                self._ready[key] = (self.clock(), value)
                self._ready.move_to_end(key)
                while len(self._ready) > self.max_entries:
                    self._ready.popitem(last=False)
            return value
        finally:
            # Never retain an exception/traceback and its large query locals.
            with self._lock:
                self._inflight.pop(key, None)
                event.set()
            self._slots.release()

    def status(self):
        with self._lock:
            return {'active_queries': len(self._inflight), 'cached_queries': len(self._ready),
                    'cache_ttl_seconds': self.ttl, 'max_cached_queries': self.max_entries}
