"""Bounded, thread-safe operation lifecycle; no Blender dependencies.

Only ``pump`` invokes scene callables. A timed-out queued operation is terminal;
running work is never interrupted. Idempotency and results last for the bounded
history window, so clients must query an ambiguous operation before resubmitting.
"""
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import contextvars
import json
import threading
import time
import uuid

_operation_context = contextvars.ContextVar("bridge_operation_id", default="")


def current_operation_id():
    return _operation_context.get()


class OperationTimeout(TimeoutError):
    def __init__(self, operation_id):
        super().__init__("Timed out waiting for operation " + operation_id)
        self.operation_id = operation_id


class AdmissionError(RuntimeError):
    pass


@dataclass
class DeferredCall:
    """Work receives only captured Python data; finish executes in the pump."""
    work: object
    finish: object


@dataclass
class Operation:
    operation_id: str
    signature: str
    fn: object
    deadline: float
    state: str = "queued"
    result: object = None
    error: object = None
    event: threading.Event = field(default_factory=threading.Event)
    retained_bytes: int = 0


class OperationQueue:
    def __init__(self, *, capacity=128, history=256, result_bytes=32 * 1024 * 1024):
        self.capacity, self.history, self.result_bytes = capacity, history, result_bytes
        self._lock = threading.RLock()
        self._pending = deque()
        self._records = OrderedDict()
        self._accepting = True
        self._workers = None
        self._completions = deque()
        self._worker_operations = set()

    def open(self):
        with self._lock:
            self._accepting = True

    def submit(self, fn, timeout, *, operation_id=None, signature=""):
        operation_id = operation_id or uuid.uuid4().hex
        if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 128:
            raise ValueError("operation_id must be a string of 1 to 128 characters")
        with self._lock:
            existing = self._records.get(operation_id)
            if existing:
                if existing.signature != signature:
                    raise ValueError("operation_id already belongs to different arguments")
                return existing
            if not self._accepting:
                raise AdmissionError("Bridge is stopping")
            if sum(not op.event.is_set() for op in self._records.values()) >= self.capacity:
                raise AdmissionError("Bridge operation capacity reached; retry after pending work finishes")
            op = Operation(operation_id, signature, fn, time.monotonic() + float(timeout))
            self._records[operation_id] = op
            self._pending.append(op)
            return op

    def _finish(self, op, state, result=None, error=None):
        op.state, op.result, op.error, op.fn = state, result, error, None
        op.retained_bytes = len(json.dumps(result, default=str).encode("utf-8")) if result is not None else 0
        op.event.set()
        completed = [item for item in self._records.values() if item.event.is_set()]
        retained = sum(item.retained_bytes for item in completed)
        while completed and (len(completed) > self.history or retained > self.result_bytes):
            oldest = completed.pop(0)
            retained -= oldest.retained_bytes
            self._records.pop(oldest.operation_id, None)

    def wait(self, op, timeout):
        if not op.event.wait(float(timeout)):
            with self._lock:
                if op.state == "queued":
                    self._pending.remove(op)
                    self._finish(op, "expired")
                elif op.event.is_set():
                    return self._outcome(op)
            raise OperationTimeout(op.operation_id)
        return self._outcome(op)

    @staticmethod
    def _outcome(op):
        if op.state in {"expired", "cancelled"}:
            raise OperationTimeout(op.operation_id)
        if op.error:
            raise RuntimeError(op.error)
        return op.result

    def pump(self, *, max_tasks=8, budget_seconds=0.01):
        started = time.monotonic()
        count = 0
        while count < max_tasks and time.monotonic() - started < budget_seconds:
            with self._lock:
                if self._completions:
                    op, fn = self._completions.popleft()
                    if op.event.is_set():
                        continue
                elif self._pending:
                    op = self._pending.popleft()
                    if time.monotonic() >= op.deadline:
                        self._finish(op, "expired")
                        continue
                    op.state = "running"
                    fn = op.fn
                else:
                    break
            token = _operation_context.set(op.operation_id)
            try:
                result = fn()
            except Exception as exc:
                with self._lock:
                    self._finish(op, "failed", error=f"{type(exc).__name__}: {exc}")
            else:
                with self._lock:
                    if isinstance(result, DeferredCall):
                        self._defer(op, result)
                    else:
                        self._finish(op, "completed", result=result)
            finally:
                _operation_context.reset(token)
            count += 1
        return count

    def _defer(self, op, call):
        if self._workers is None:
            self._workers = ThreadPoolExecutor(max_workers=4, thread_name_prefix="BridgeIO")
        op.fn = None
        self._worker_operations.add(op.operation_id)
        context = contextvars.copy_context()
        future = self._workers.submit(context.run, call.work)
        def ready(completed):
            with self._lock:
                self._worker_operations.discard(op.operation_id)
                if op.event.is_set():
                    return
                try:
                    value = completed.result()
                except Exception as exc:
                    value = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
                self._completions.append((op, lambda: call.finish(value)))
        future.add_done_callback(ready)

    def status(self, operation_id):
        with self._lock:
            op = self._records.get(operation_id)
            if op is None:
                return None
            return {"operation_id": op.operation_id, "state": op.state,
                    "request_may_still_be_running": op.state == "running",
                    "result": op.result, "error": op.error}

    def empty(self):
        with self._lock:
            return not self._pending and not self._completions

    def close(self):
        with self._lock:
            self._accepting = False
            while self._pending:
                self._finish(self._pending.popleft(), "cancelled")
            for op in list(self._records.values()):
                if op.operation_id in self._worker_operations:
                    self._finish(op, "cancelled")
            while self._completions:
                op, _ = self._completions.popleft()
                self._finish(op, "cancelled")
            if self._workers:
                self._workers.shutdown(wait=False, cancel_futures=True)
                self._workers = None
