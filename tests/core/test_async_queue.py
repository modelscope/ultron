# Copyright (c) ModelScope Contributors. All rights reserved.
import asyncio
import unittest
from unittest.mock import MagicMock

from ultron.core.async_queue import EmbeddingQueue, EmbeddingTask


class TestEmbeddingTask(unittest.TestCase):
    def test_wait_returns_result(self):
        async def run():
            t = EmbeddingTask(task_id="1", text="hi")
            t.result = [1.0, 0.0]
            t._event.set()
            return await t.wait(timeout=1.0)

        self.assertEqual(asyncio.run(run()), [1.0, 0.0])

    def test_wait_timeout_returns_none(self):
        async def run():
            t = EmbeddingTask(task_id="2", text="hi")
            # Don't set the event — should timeout
            result = await t.wait(timeout=0.05)
            return result, t.error

        result, error = asyncio.run(run())
        self.assertIsNone(result)
        self.assertIn("timed out", error.lower())

    def test_initial_state(self):
        t = EmbeddingTask(task_id="x", text="hello")
        self.assertIsNone(t.result)
        self.assertIsNone(t.error)
        self.assertFalse(t.done)


class TestEmbeddingQueue(unittest.TestCase):
    def test_submit_requires_start(self):
        async def run():
            emb = MagicMock()
            q = EmbeddingQueue(emb, max_size=4, workers=1)
            with self.assertRaises(RuntimeError):
                await q.submit("x")

        asyncio.run(run())

    def test_embed_flow(self):
        async def run():
            emb = MagicMock()
            emb.embed_text.return_value = [0.0, 1.0]
            q = EmbeddingQueue(emb, max_size=8, workers=1)
            await q.start()
            try:
                task = await q.submit("hello")
                vec = await task.wait(timeout=5.0)
                self.assertEqual(vec, [0.0, 1.0])
                emb.embed_text.assert_called()
            finally:
                await q.shutdown()

        asyncio.run(run())

    def test_get_stats(self):
        async def run():
            emb = MagicMock()
            emb.embed_text.return_value = [1.0]
            q = EmbeddingQueue(emb, workers=1)
            await q.start()
            try:
                st = q.get_stats()
                self.assertTrue(st["running"])
                self.assertEqual(st["workers"], 1)
            finally:
                await q.shutdown()

        asyncio.run(run())

    def test_is_running_lifecycle(self):
        async def run():
            emb = MagicMock()
            q = EmbeddingQueue(emb, workers=1)
            self.assertFalse(q.is_running)
            await q.start()
            self.assertTrue(q.is_running)
            await q.shutdown()
            self.assertFalse(q.is_running)

        asyncio.run(run())

    def test_start_idempotent(self):
        async def run():
            emb = MagicMock()
            q = EmbeddingQueue(emb, workers=1)
            await q.start()
            await q.start()  # second start should be no-op
            try:
                self.assertTrue(q.is_running)
            finally:
                await q.shutdown()

        asyncio.run(run())

    def test_callback_invoked(self):
        async def run():
            emb = MagicMock()
            emb.embed_text.return_value = [0.5]
            q = EmbeddingQueue(emb, workers=1)
            await q.start()
            try:
                callback_results = []
                task = await q.submit("text")
                task.callback = lambda t: callback_results.append(t.result)
                await task.wait(timeout=5.0)
                # Give callback a moment to fire
                await asyncio.sleep(0.05)
                self.assertEqual(callback_results, [[0.5]])
            finally:
                await q.shutdown()

        asyncio.run(run())

    def test_embed_error_sets_task_error(self):
        async def run():
            emb = MagicMock()
            emb.embed_text.side_effect = RuntimeError("embed failed")
            q = EmbeddingQueue(emb, workers=1)
            await q.start()
            try:
                task = await q.submit("text")
                result = await task.wait(timeout=5.0)
                self.assertIsNone(result)
                self.assertIn("embed failed", task.error)
            finally:
                await q.shutdown()

        asyncio.run(run())

    def test_multiple_tasks(self):
        async def run():
            emb = MagicMock()
            emb.embed_text.return_value = [1.0, 0.0]
            q = EmbeddingQueue(emb, max_size=10, workers=2)
            await q.start()
            try:
                tasks = [await q.submit(f"text {i}") for i in range(5)]
                results = [await t.wait(timeout=5.0) for t in tasks]
                self.assertEqual(len(results), 5)
                self.assertTrue(all(r == [1.0, 0.0] for r in results))
            finally:
                await q.shutdown()

        asyncio.run(run())

    def test_stats_queue_size(self):
        async def run():
            emb = MagicMock()
            q = EmbeddingQueue(emb, workers=1)
            await q.start()
            try:
                st = q.get_stats()
                self.assertIn("queue_size", st)
                self.assertIn("pending_count", st)
                self.assertIn("max_size", st)
            finally:
                await q.shutdown()

        asyncio.run(run())

    def test_custom_task_id(self):
        async def run():
            emb = MagicMock()
            emb.embed_text.return_value = [0.1]
            q = EmbeddingQueue(emb, workers=1)
            await q.start()
            try:
                task = await q.submit("text", task_id="my-custom-id")
                self.assertEqual(task.task_id, "my-custom-id")
                await task.wait(timeout=5.0)
            finally:
                await q.shutdown()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
