from typing import List
import os
import requests
from contextvars import ContextVar

# Per-request override (set by API when frontend sends embedding_provider/model)
_embedding_provider_ctx: ContextVar[str | None] = ContextVar("embedding_provider", default=None)
_embedding_model_ctx: ContextVar[str | None] = ContextVar("embedding_model", default=None)

# Default from env; "ollama" for local, "openai" for Cloud Run
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))

OPENAI_EMBED_MODELS = ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"]
OLLAMA_EMBED_MODELS = ["bge-m3", "nomic-embed-text", "mxbai-embed-large"]


def _get_provider() -> str:
    return _embedding_provider_ctx.get() or EMBEDDING_PROVIDER


def _get_model(provider: str) -> str:
    override = _embedding_model_ctx.get()
    if override:
        return override
    return OPENAI_EMBED_MODEL if provider == "openai" else OLLAMA_EMBED_MODEL


def set_embedding_override(provider: str | None, model: str | None) -> None:
    """Set per-request embedding override (call at start of request)."""
    if provider is not None:
        _embedding_provider_ctx.set(provider)
    if model is not None:
        _embedding_model_ctx.set(model)


def embed_text(text: str) -> List[float]:
    """Single-text embed; for many chunks use embed_texts() to avoid N requests."""
    provider = _get_provider()
    model = _get_model(provider)
    if provider == "openai":
        return _embed_text_openai(text, model)
    if provider == "ollama":
        return _embed_text_ollama(text, model)
    raise Exception(f"不支持的嵌入 provider: {provider}")


def embed_texts(texts: List[str], batch_size: int = None) -> List[List[float]]:
    """Batch embed many texts with fewer HTTP requests."""
    if not texts:
        return []
    provider = _get_provider()
    model = _get_model(provider)
    batch_size = batch_size or EMBEDDING_BATCH_SIZE
    if provider == "openai":
        return _embed_batch_openai(texts, model, batch_size)
    if provider == "ollama":
        return _embed_batch_ollama(texts, model, batch_size)
    raise Exception(f"不支持的嵌入 provider: {provider}")


def _embed_text_openai(text: str, model: str) -> List[float]:
    """Use OpenAI Embeddings API."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.embeddings.create(input=text, model=model)
    if resp.data and len(resp.data) > 0:
        return resp.data[0].embedding
    raise Exception("OpenAI embedding 返回空")


def _embed_batch_openai(texts: List[str], model: str, batch_size: int) -> List[List[float]]:
    """Batch embed via OpenAI API."""
    from openai import OpenAI
    client = OpenAI()
    out: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(input=batch, model=model)
        if resp.data:
            for d in sorted(resp.data, key=lambda x: x.index):
                out.append(d.embedding)
    return out


def _embed_text_ollama(text: str, model: str) -> List[float]:
    """
    使用 Ollama 本地模型进行文本嵌入
    支持新版 /api/embed 和旧版 /api/embeddings 两种 API
    """
    last_error = None

    try:
        url = f"{OLLAMA_BASE_URL}/api/embed"
        payload = {"model": model, "input": text}
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        vectors = result.get("embeddings")
        if vectors and isinstance(vectors, list) and len(vectors) > 0:
            return vectors[0]
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        if e.response is not None:
            try:
                error_detail = e.response.text[:500]
            except Exception:
                pass
        if e.response is not None and e.response.status_code not in (400, 404, 500):
            raise Exception(f"Ollama embedding 请求失败: {str(e)} | {error_detail}")
        last_error = str(e)
    except requests.exceptions.RequestException as e:
        last_error = str(e)

    try:
        url = f"{OLLAMA_BASE_URL}/api/embeddings"
        payload = {"model": model, "prompt": text}
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        embedding = result.get("embedding")
        if embedding and isinstance(embedding, list):
            return embedding
        raise Exception(f"Ollama 返回格式异常: {result}")
    except requests.exceptions.RequestException as e:
        raise Exception(
            f"Ollama embedding 请求失败: {str(e)}\n"
            f"请确保已安装模型: ollama pull {model}"
        )


def _embed_batch_ollama(texts: List[str], model: str, batch_size: int) -> List[List[float]]:
    """Call Ollama /api/embed with input as list of strings (batch)."""
    out: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            url = f"{OLLAMA_BASE_URL}/api/embed"
            payload = {"model": model, "input": batch}
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            vectors = result.get("embeddings")
            if vectors and isinstance(vectors, list) and len(vectors) == len(batch):
                out.extend(vectors)
            else:
                for t in batch:
                    out.append(_embed_text_ollama(t, model))
        except Exception:
            for t in batch:
                out.append(_embed_text_ollama(t, model))
    return out
