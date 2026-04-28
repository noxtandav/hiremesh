"""Embeddings via LiteLLM, with a deterministic `fake` mode for dev/tests.

The fake mode is intentionally smarter than a hash dump: each token contributes
to a stable bag of dims, so docs that share tokens land near each other in
cosine space. Good enough to demo semantic search without an API key — not a
substitute for a real model.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable

from app.core.config import get_settings
from app.models.embedding import EMBEDDING_DIM

_TOKEN_RE = re.compile(r"[A-Za-z0-9+#./_-]{2,}")


def _is_fake() -> bool:
    return get_settings().llm_embed_model.lower() == "fake"


# ----- fake embedder -----------------------------------------------------


def _tokens(text: str) -> Iterable[str]:
    for tok in _TOKEN_RE.findall(text.lower()):
        if len(tok) > 1:
            yield tok


def _stable_dims(token: str, n: int = 8) -> list[int]:
    """For a token, return `n` dim indices it contributes to.

    Hashing into a fixed set per token keeps everything deterministic.
    """
    h = hashlib.sha256(token.encode()).digest()
    return [
        int.from_bytes(h[i : i + 4], "big") % EMBEDDING_DIM
        for i in range(0, n * 4, 4)
    ]


def _stable_signs(token: str, n: int = 8) -> list[int]:
    h = hashlib.md5(token.encode()).digest()
    return [1 if (h[i] & 1) else -1 for i in range(n)]


def fake_embed(text: str) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    for tok in _tokens(text):
        for d, s in zip(_stable_dims(tok), _stable_signs(tok)):
            vec[d] += float(s)
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


# ----- public api --------------------------------------------------------


def embed(text: str) -> list[float]:
    """Embed a single document. Returns an L2-normalized vector whose dim
    matches the configured embedding model."""
    if _is_fake():
        return fake_embed(text)

    import litellm  # local import — keeps fake mode startup fast

    s = get_settings()
    kwargs: dict = {"model": s.llm_embed_model, "input": [text]}
    # Only pass api_key if explicitly set; otherwise LiteLLM reads the right
    # provider env var (OPENROUTER_API_KEY, OPENAI_API_KEY, etc.).
    if s.llm_api_key:
        kwargs["api_key"] = s.llm_api_key

    response = litellm.embedding(**kwargs)
    raw = response["data"][0]["embedding"]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw] if norm else list(raw)


def probe_dim() -> int:
    """Run one embedding call to discover the model's actual output dim.

    Used by the admin reset endpoint to verify that the configured dim and
    the model dim agree before recreating the table.
    """
    return len(embed("dim probe"))
