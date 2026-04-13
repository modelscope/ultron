# Copyright (c) ModelScope Contributors. All rights reserved.
import importlib.util
import os
from http import HTTPStatus
from typing import List, Union

HAS_NUMPY = importlib.util.find_spec("numpy") is not None

try:
    import dashscope

    HAS_DASHSCOPE = True
except ImportError:
    HAS_DASHSCOPE = False


class EmbeddingService:
    """
    DashScope TextEmbedding client: model default text-embedding-v4, requires DASHSCOPE_API_KEY.

    Raises RuntimeError when dashscope is missing, the key is unset, or the API returns an error.
    Empty embedding input raises ValueError from embed_text.
    """

    def __init__(
        self,
        model_name: str = "text-embedding-v4",
        *,
        embedding_dimension_hint: int = 1024,
        request_timeout_seconds: int = 300,
    ):
        if not HAS_DASHSCOPE:
            raise RuntimeError(
                "dashscope is not installed; run: pip install dashscope"
            )
        self.model_name = model_name
        self._backend = "dashscope"
        self._request_timeout_seconds = max(30, int(request_timeout_seconds))
        env_dim = os.environ.get("ULTRON_EMBEDDING_DIMENSION", "").strip()
        self._dimension = int(env_dim) if env_dim else int(embedding_dimension_hint)

    @staticmethod
    def _require_api_key() -> None:
        if not os.environ.get("DASHSCOPE_API_KEY", "").strip():
            raise RuntimeError(
                "DASHSCOPE_API_KEY is not set; DashScope TextEmbedding cannot be called"
            )

    @property
    def dimension(self) -> int:
        return self._dimension

    def _embed_dashscope(self, inputs: List[str]) -> List[List[float]]:
        if not inputs:
            return []
        self._require_api_key()
        dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        api_input: Union[str, List[str]] = inputs[0] if len(inputs) == 1 else inputs
        try:
            resp = dashscope.TextEmbedding.call(
                model=self.model_name,
                input=api_input,
                request_timeout=self._request_timeout_seconds,
            )
        except Exception as e:
            raise RuntimeError(f"DashScope TextEmbedding call failed: {e}") from e

        if resp.status_code != HTTPStatus.OK:
            msg = getattr(resp, "message", "") or getattr(resp, "code", "")
            raise RuntimeError(f"DashScope TextEmbedding error: {msg}")

        out = getattr(resp, "output", None) or {}
        raw = out.get("embeddings") or []
        if not raw:
            raise RuntimeError("DashScope TextEmbedding response has no embeddings")

        rows: List[List[float]] = []
        for item in raw:
            vec = item.get("embedding") if isinstance(item, dict) else None
            if not vec:
                raise RuntimeError("DashScope returned an empty embedding row")
            rows.append([float(x) for x in vec])
            self._dimension = len(rows[-1])

        if len(rows) != len(inputs):
            raise RuntimeError(
                f"embedding count mismatch: got {len(rows)}, expected {len(inputs)}"
            )
        return rows

    def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("cannot embed empty text")
        rows = self._embed_dashscope([text])
        if not rows:
            raise RuntimeError("DashScope TextEmbedding returned no vectors")
        return rows[0]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        cleaned = [t if t and t.strip() else " " for t in texts]
        if not cleaned:
            return []
        return self._embed_dashscope(cleaned)

    @staticmethod
    def _take(text: str, max_len: int) -> str:
        if not text:
            return ""
        return text[:max_len]

    def embed_skill(self, name: str, description: str, content: str) -> List[float]:
        body = self._take(content, 500)
        return self.embed_text(f"{name} {description} {body}")

    def embed_memory_context(
        self,
        memory_type: str,
        content: str,
        context: str,
        resolution: str,
    ) -> List[float]:
        return self.embed_text(
            f"memory type: {memory_type} "
            f"content: {self._take(content, 300)} "
            f"context: {self._take(context, 200)} "
            f"resolution: {self._take(resolution, 200)}"
        )

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(x * y for x, y in zip(vec1, vec2))
        norm_a = sum(x * x for x in vec1) ** 0.5
        norm_b = sum(y * y for y in vec2) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def is_available(self) -> bool:
        return bool(os.environ.get("DASHSCOPE_API_KEY", "").strip()) and HAS_DASHSCOPE

    def get_model_info(self) -> dict:
        return {
            "backend": self._backend,
            "model_name": self.model_name,
            "dimension": self._dimension,
            "is_available": self.is_available(),
            "has_dashscope": HAS_DASHSCOPE,
            "has_numpy": HAS_NUMPY,
            "request_timeout_seconds": self._request_timeout_seconds,
        }