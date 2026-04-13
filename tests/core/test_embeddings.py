# Copyright (c) ModelScope Contributors. All rights reserved.
import os
import unittest
from http import HTTPStatus
from unittest.mock import MagicMock, patch

from ultron.core.embeddings import HAS_DASHSCOPE, EmbeddingService


class TestCosineSimilarity(unittest.TestCase):
    """Cosine similarity helper without DashScope."""

    def setUp(self):
        self.svc = object.__new__(EmbeddingService)

    def test_identical_unit_vectors(self):
        self.assertAlmostEqual(
            self.svc.cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]),
            1.0,
        )

    def test_orthogonal(self):
        self.assertAlmostEqual(
            self.svc.cosine_similarity([1.0, 0.0], [0.0, 1.0]),
            0.0,
        )

    def test_empty_or_mismatch_returns_zero(self):
        self.assertEqual(self.svc.cosine_similarity([], [1.0]), 0.0)
        self.assertEqual(self.svc.cosine_similarity([1.0, 0.0], [1.0]), 0.0)


class TestEmbedTextValidation(unittest.TestCase):
    """embed_text input checks (no network)."""

    def setUp(self):
        self.svc = object.__new__(EmbeddingService)

    def test_empty_text_raises(self):
        with self.assertRaises(ValueError):
            self.svc.embed_text("")
        with self.assertRaises(ValueError):
            self.svc.embed_text("   ")


class TestComposeWithoutApi(unittest.TestCase):
    """Structured prompts call embed_text with expected slices."""

    def setUp(self):
        self.svc = object.__new__(EmbeddingService)
        self.svc.embed_text = MagicMock(return_value=[0.5, 0.5])

    def test_embed_memory_context_truncation(self):
        long_c = "c" * 500
        self.svc.embed_memory_context("pattern", long_c, "ctx", "res")
        arg = self.svc.embed_text.call_args[0][0]
        self.assertIn("memory type: pattern", arg)
        start = arg.index("content: ") + len("content: ")
        end = arg.index(" context:", start)
        self.assertEqual(end - start, 300)

    def test_embed_skill_truncates_content(self):
        self.svc.embed_skill("n", "d", "x" * 600)
        arg = self.svc.embed_text.call_args[0][0]
        self.assertIn("x" * 500, arg)
        self.assertNotIn("x" * 501, arg)


class TestDashScopeIntegration(unittest.TestCase):
    """EmbeddingService with mocked DashScope HTTP client."""

    class _OkResp:
        status_code = HTTPStatus.OK

        def __init__(self, vectors):
            self.output = {"embeddings": [{"embedding": v} for v in vectors]}

    @unittest.skipUnless(HAS_DASHSCOPE, "dashscope not installed")
    def test_embed_text_updates_dimension(self):
        vec = [0.0, 1.0, 2.0]
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}):
            with patch("ultron.core.embeddings.dashscope") as mock_ds:
                mock_ds.TextEmbedding.call.return_value = self._OkResp([vec])
                svc = EmbeddingService(embedding_dimension_hint=8)
                out = svc.embed_text("hello")
                self.assertEqual(out, vec)
                self.assertEqual(svc.dimension, 3)
                self.assertTrue(svc.is_available())

    @unittest.skipUnless(HAS_DASHSCOPE, "dashscope not installed")
    def test_missing_key_raises(self):
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": ""}):
            with patch("ultron.core.embeddings.dashscope"):
                svc = EmbeddingService()
                with self.assertRaises(RuntimeError):
                    svc.embed_text("hi")

    @unittest.skipUnless(HAS_DASHSCOPE, "dashscope not installed")
    def test_api_error_raises(self):
        bad = MagicMock()
        bad.status_code = 500
        bad.message = "quota"
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "k"}):
            with patch("ultron.core.embeddings.dashscope") as mock_ds:
                mock_ds.TextEmbedding.call.return_value = bad
                svc = EmbeddingService()
                with self.assertRaises(RuntimeError) as ctx:
                    svc.embed_text("x")
                self.assertIn("quota", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
