# Copyright (c) ModelScope Contributors. All rights reserved.
import importlib.util
import os
from http import HTTPStatus
from typing import List, Union

HAS_NUMPY = importlib.util.find_spec("numpy") is not None
HAS_SENTENCE_TRANSFORMERS = importlib.util.find_spec("sentence_transformers") is not None

try:
    import dashscope

    HAS_DASHSCOPE = True
except ImportError:
    HAS_DASHSCOPE = False


class EmbeddingService:
    """
    Embedding client with two backends:
    - dashscope: default TextEmbedding API, requires DASHSCOPE_API_KEY.
    - local: sentence-transformers model loaded locally.

    Raises RuntimeError when required dependency/key is missing or backend call fails.
    Empty embedding input raises ValueError from embed_text.
    """

    def __init__(
        self,
        backend: str = "dashscope",
        model_name: str = "text-embedding-v4",
        *,
        embedding_dimension_hint: int = 1024,
        request_timeout_seconds: int = 300,
    ):
        self._backend = (backend or "dashscope").strip().lower()
        if self._backend not in {"dashscope", "local"}:
            raise RuntimeError(
                f"unsupported embedding backend: {self._backend}, expected dashscope or local"
            )

        self.model_name = model_name
        self._request_timeout_seconds = max(30, int(request_timeout_seconds))
        env_dim = os.environ.get("ULTRON_EMBEDDING_DIMENSION", "").strip()
        self._dimension = int(env_dim) if env_dim else int(embedding_dimension_hint)
        self._local_model = None

        if self._backend == "dashscope":
            if not HAS_DASHSCOPE:
                raise RuntimeError(
                    "dashscope is not installed; run: pip install dashscope"
                )
        else:
            self._init_local_model()

    def _init_local_model(self) -> None:
        if not HAS_SENTENCE_TRANSFORMERS:
            raise RuntimeError(
                "sentence-transformers is not installed; run: pip install sentence-transformers transformers"
            )
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as e:
            raise RuntimeError(f"failed to import sentence-transformers: {e}") from e
        try:
            self._local_model = SentenceTransformer(self.model_name)
            dim = getattr(self._local_model, "get_sentence_embedding_dimension", None)
            if callable(dim):
                got = dim()
                if got:
                    self._dimension = int(got)
        except Exception as e:
            raise RuntimeError(
                f"failed to load local embedding model '{self.model_name}': {e}"
            ) from e

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
        if self._backend == "local":
            assert self._local_model is not None
            rows = self._local_model.encode([text], convert_to_numpy=False)
            if not rows:
                raise RuntimeError("local embedding model returned no vectors")
            vec = [float(x) for x in rows[0]]
            self._dimension = len(vec)
            return vec
        rows = self._embed_dashscope([text])
        if not rows:
            raise RuntimeError("DashScope TextEmbedding returned no vectors")
        return rows[0]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        cleaned = [t if t and t.strip() else " " for t in texts]
        if not cleaned:
            return []
        if self._backend == "local":
            assert self._local_model is not None
            rows = self._local_model.encode(cleaned, convert_to_numpy=False)
            out = [[float(x) for x in row] for row in rows]
            if out:
                self._dimension = len(out[0])
            return out
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
        if self._backend == "local":
            return self._local_model is not None
        return bool(os.environ.get("DASHSCOPE_API_KEY", "").strip()) and HAS_DASHSCOPE

    def get_model_info(self) -> dict:
        return {
            "backend": self._backend,
            "model_name": self.model_name,
            "dimension": self._dimension,
            "is_available": self.is_available(),
            "has_dashscope": HAS_DASHSCOPE,
            "has_sentence_transformers": HAS_SENTENCE_TRANSFORMERS,
            "has_numpy": HAS_NUMPY,
            "request_timeout_seconds": self._request_timeout_seconds,
        }