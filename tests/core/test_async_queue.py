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


if __name__ == "__main__":
    unittest.main()
