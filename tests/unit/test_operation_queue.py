import importlib.util
from pathlib import Path
import sys
import threading
import time
import unittest

spec = importlib.util.spec_from_file_location("operation_queue", Path(__file__).resolve().parents[2] / "addon/claude_blender/operation_queue.py")
queue = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = queue
spec.loader.exec_module(queue)


class OperationQueueTests(unittest.TestCase):
    def test_timeout_before_start_never_executes(self):
        q, effects = queue.OperationQueue(), []
        op = q.submit(lambda: effects.append(1), 30)
        with self.assertRaises(queue.OperationTimeout):
            q.wait(op, 0)
        q.pump()
        self.assertEqual(effects, [])
        self.assertEqual(q.status(op.operation_id)["state"], "expired")

    def test_running_timeout_can_recover_and_deduplicate(self):
        q = queue.OperationQueue()
        entered, release = threading.Event(), threading.Event()
        effects = []
        def run():
            entered.set()
            release.wait(2)
            effects.append(1)
            return {"ok": True}
        op = q.submit(run, 30, operation_id="same", signature="args")
        worker = threading.Thread(target=q.pump)
        worker.start()
        self.assertTrue(entered.wait(2))
        try:
            with self.assertRaises(queue.OperationTimeout):
                q.wait(op, 0)
            self.assertEqual(q.status("same")["state"], "running")
            self.assertIs(q.submit(run, 30, operation_id="same", signature="args"), op)
        finally:
            release.set()
            worker.join(2)
        self.assertEqual(q.wait(op, 0), {"ok": True})
        self.assertEqual(effects, [1])
        with self.assertRaises(ValueError):
            q.submit(run, 30, operation_id="same", signature="different")

    def test_capacity_tick_budget_shutdown_and_retention(self):
        q = queue.OperationQueue(capacity=2, history=1)
        first = q.submit(lambda: 1, 30)
        second = q.submit(lambda: 2, 30)
        with self.assertRaises(queue.AdmissionError):
            q.submit(lambda: 3, 30)
        self.assertEqual(q.pump(max_tasks=1), 1)
        self.assertEqual(q.status(second.operation_id)["state"], "queued")
        q.close()
        self.assertEqual(q.status(second.operation_id)["state"], "cancelled")
        self.assertIsNone(q.status(first.operation_id))
        with self.assertRaises(queue.AdmissionError):
            q.submit(lambda: 3, 30)
        q.open()
        expired = q.submit(lambda: self.fail("expired work ran"), -1)
        q.pump()
        self.assertEqual(q.status(expired.operation_id)["state"], "expired")

    def test_blocked_worker_does_not_block_main_and_finishes_on_main(self):
        q = queue.OperationQueue()
        entered, release = threading.Event(), threading.Event()
        main_thread = threading.get_ident()
        def work():
            self.assertNotEqual(threading.get_ident(), main_thread)
            self.assertEqual(queue.current_operation_id(), op.operation_id)
            entered.set()
            release.wait(2)
            return 42
        def finish(value):
            self.assertEqual(threading.get_ident(), main_thread)
            self.assertEqual(queue.current_operation_id(), op.operation_id)
            return value
        op = q.submit(lambda: queue.DeferredCall(work, finish), 30)
        try:
            q.pump()
            self.assertTrue(entered.wait(2))
            heartbeat = q.submit(lambda: "responsive", 30)
            q.pump()
            self.assertEqual(q.wait(heartbeat, 0), "responsive")
            release.set()
            deadline = time.monotonic() + 2
            while not op.event.is_set() and time.monotonic() < deadline:
                q.pump()
                time.sleep(0.001)
            self.assertEqual(q.wait(op, 0), 42)
            self.assertEqual(queue.current_operation_id(), "")
        finally:
            release.set()
            q.close()

    def test_shutdown_discards_worker_finalizer(self):
        q = queue.OperationQueue()
        entered, release = threading.Event(), threading.Event()
        def work():
            entered.set()
            release.wait(2)
        op = q.submit(lambda: queue.DeferredCall(work, lambda _: self.fail("finalized after shutdown")), 30)
        try:
            q.pump()
            self.assertTrue(entered.wait(2))
            q.close()
            q.open()
            release.set()
            q.pump()
            self.assertEqual(q.status(op.operation_id)["state"], "cancelled")
        finally:
            release.set()
            q.close()


if __name__ == "__main__":
    unittest.main()
