"""Ollama LLM provider implementation using HTTPX."""

import json
import os
import time
from collections.abc import Generator
from typing import Any

import httpx

from commit_cli.diagnostics import ModelDiagnostics
from commit_cli.git.chunking import DEFAULT_FALLBACK_CONTEXT_WINDOW
from commit_cli.exceptions import (
    GenerationTimeoutError,
    IncompleteGenerationError,
    ModelNotFoundError,
    ProviderError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from commit_cli.models import GenerationRequest, GenerationResponse, StreamChunk
from commit_cli.providers.base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """Local Ollama generation provider."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
        connect_timeout: float = 5.0,
        read_timeout: float = 60.0,
        timeout: float = 120.0,
        keep_alive: str = "5m",
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._timeout = timeout
        self._keep_alive = keep_alive
        self._client = client
        self._owns_client = client is None
        self._detected_num_ctx: int | None = None
        self._cached_show_data: dict[str, Any] | None = None
        self._cached_context_reason: str = "Unknown"
        self._cached_context_confidence: str = "Unknown"

    @property
    def provider_name(self) -> str:
        return "Ollama"

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        self._client = httpx.Client(
            timeout=httpx.Timeout(
                self._read_timeout,
                connect=self._connect_timeout,
                read=self._read_timeout,
                write=self._read_timeout,
            )
        )
        return self._client

    def close(self) -> None:
        """Close HTTP client resources if owned by this provider instance."""
        if self._owns_client and self._client is not None and not self._client.is_closed:
            self._client.close()

    def __enter__(self) -> "OllamaProvider":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def check_availability(self) -> bool:
        """Check if Ollama server is running and reachable."""
        client = self._get_client()
        try:
            res = client.get(f"{self._base_url}/", timeout=self._connect_timeout)
            return res.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            return False

    def get_installed_models(self) -> list[str]:
        """Fetch list of model tags currently installed on Ollama."""
        client = self._get_client()
        url = f"{self._base_url}/api/tags"
        try:
            res = client.get(url, timeout=self._connect_timeout)
        except httpx.ConnectError as e:
            raise ProviderUnavailableError(
                provider=self.provider_name,
                url=self._base_url,
                reason=f"Could not connect to server: {e}",
            ) from e
        except httpx.TimeoutException as e:
            raise ProviderUnavailableError(
                provider=self.provider_name,
                url=self._base_url,
                reason=f"Connection timed out after {self._connect_timeout:.1f}s.",
            ) from e

        if res.status_code != 200:
            raise ProviderError(
                f"Ollama returned HTTP {res.status_code} while querying installed models."
            )

        try:
            data = res.json()
            models = [m["name"] for m in data.get("models", []) if "name" in m]
            return models
        except Exception as e:
            raise ProviderError(f"Failed to parse Ollama model tags: {e}") from e

    def get_context_window(self) -> int | None:
        """Query Ollama /api/show to determine the active model's context window length in tokens.

        Considers:
        1. COMMIT_NUM_CTX or OLLAMA_NUM_CTX environment variable overrides.
        2. Modelfile parameters for num_ctx.
        3. Model architecture metadata for context_length.
        Caches and aligns the effective context window for subsequent generation requests.
        """
        if self._detected_num_ctx is not None:
            return self._detected_num_ctx

        # 1. Check environment variable override
        for env_key in ("COMMIT_NUM_CTX", "OLLAMA_NUM_CTX"):
            env_val = os.environ.get(env_key, "").strip()
            if env_val:
                try:
                    val = int(env_val)
                    if val > 0:
                        self._detected_num_ctx = val
                        self._cached_context_reason = f"Environment variable {env_key}={val}"
                        self._cached_context_confidence = "Configured"
                        return val
                except ValueError:
                    pass

        client = self._get_client()
        url = f"{self._base_url}/api/show"
        try:
            res = client.post(url, json={"name": self._model, "model": self._model}, timeout=self._connect_timeout)
            if res.status_code == 200:
                data = res.json()
                self._cached_show_data = data
                # 2. Check parameters for num_ctx in modelfile
                params_str = data.get("parameters", "")
                if params_str:
                    for line in params_str.splitlines():
                        parts = line.strip().split()
                        if len(parts) >= 2 and parts[0] == "num_ctx":
                            try:
                                ctx = int(parts[1])
                                if ctx > 0:
                                    self._detected_num_ctx = ctx
                                    self._cached_context_reason = f"Modelfile parameter 'num_ctx {ctx}'"
                                    self._cached_context_confidence = "Configured"
                                    return ctx
                            except ValueError:
                                pass

                # 3. Check model_info for context_length
                model_info = data.get("model_info", {})
                for k, v in model_info.items():
                    if k.endswith(".context_length") and isinstance(v, int):
                        if v > 0:
                            # Advertised architectural context length from GGUF metadata.
                            # Cap runtime default context to 8192 tokens unless explicitly overridden
                            # via COMMIT_NUM_CTX, OLLAMA_NUM_CTX, or Modelfile parameters to prevent
                            # massive KV-cache allocation and read timeouts on local hardware.
                            runtime_ctx = min(v, 8192)
                            self._detected_num_ctx = runtime_ctx
                            if runtime_ctx < v:
                                self._cached_context_reason = f"Model metadata (advertised {v}, capped to {runtime_ctx})"
                            else:
                                self._cached_context_reason = f"Model metadata ({v} tokens)"
                            self._cached_context_confidence = "Estimated"
                            return runtime_ctx
        except Exception:
            pass

        if self._detected_num_ctx is None:
            self._detected_num_ctx = DEFAULT_FALLBACK_CONTEXT_WINDOW
            self._cached_context_reason = "Default fallback context"
            self._cached_context_confidence = "Fallback"

        return self._detected_num_ctx

    def get_diagnostics(self) -> ModelDiagnostics:
        """Fetch model metadata, server version, and context observability."""
        if self._detected_num_ctx is None:
            self.get_context_window()

        client = self._get_client()

        # 1. Server version
        server_version: str | None = None
        try:
            v_res = client.get(f"{self._base_url}/api/version", timeout=self._connect_timeout)
            if v_res.status_code == 200:
                server_version = v_res.json().get("version")
        except Exception:
            pass

        # 2. Query /api/ps for loaded runtime context
        runtime_loaded_ctx: int | None = None
        try:
            ps_res = client.get(f"{self._base_url}/api/ps", timeout=self._connect_timeout)
            if ps_res.status_code == 200:
                ps_data = ps_res.json()
                for m in ps_data.get("models", []):
                    m_name = m.get("name", "")
                    m_model = m.get("model", "")
                    if m_name == self._model or m_model == self._model or m_name.startswith(self._model.split(":")[0]):
                        ctx_val = m.get("context_length") or m.get("context")
                        if isinstance(ctx_val, int) and ctx_val > 0:
                            runtime_loaded_ctx = ctx_val
                            break
        except Exception:
            pass

        # 3. Model info from cached or fetched /api/show
        show_data = self._cached_show_data
        if show_data is None:
            try:
                res = client.post(
                    f"{self._base_url}/api/show",
                    json={"name": self._model, "model": self._model},
                    timeout=self._connect_timeout,
                )
                if res.status_code == 200:
                    show_data = res.json()
                    self._cached_show_data = show_data
            except Exception:
                show_data = {}

        model_info = show_data.get("model_info", {}) if show_data else {}
        details = show_data.get("details", {}) if show_data else {}

        architecture: str | None = model_info.get("general.architecture") or details.get("family")
        parameter_size: str | None = details.get("parameter_size")
        if not parameter_size and "general.parameter_count" in model_info:
            p_count = model_info["general.parameter_count"]
            if isinstance(p_count, (int, float)):
                parameter_size = f"{p_count / 1e9:.1f}B"

        quantization_level: str | None = details.get("quantization_level")

        advertised_ctx: int | None = None
        for k, v in model_info.items():
            if k.endswith(".context_length") and isinstance(v, int):
                advertised_ctx = v
                break

        modelfile_ctx: int | None = None
        params_str = show_data.get("parameters", "") if show_data else ""
        if params_str:
            for line in params_str.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0] == "num_ctx":
                    try:
                        modelfile_ctx = int(parts[1])
                    except ValueError:
                        pass

        server_default_num_ctx = 2048

        return ModelDiagnostics(
            model_name=self._model,
            server_version=server_version,
            architecture=architecture,
            parameter_size=parameter_size,
            quantization_level=quantization_level,
            advertised_context_length=advertised_ctx,
            modelfile_num_ctx=modelfile_ctx,
            server_default_num_ctx=server_default_num_ctx,
            request_num_ctx=self._detected_num_ctx,
            runtime_loaded_num_ctx=runtime_loaded_ctx,
            context_source=self._cached_context_reason,
            context_confidence=self._cached_context_confidence,
        )

    def _build_payload(self, request: GenerationRequest, stream: bool) -> dict[str, Any]:
        effective_ctx = self.get_context_window()
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": request.prompt,
            "stream": stream,
            "keep_alive": self._keep_alive,
            "options": {
                "temperature": request.temperature,
                "num_ctx": effective_ctx,
            },
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt
        if request.response_schema is not None:
            payload["format"] = request.response_schema
        if request.max_tokens is not None:
            payload["options"]["num_predict"] = request.max_tokens
        return payload

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Execute non-streaming generation."""
        client = self._get_client()
        payload = self._build_payload(request, stream=False)
        url = f"{self._base_url}/api/generate"
        start_time = time.monotonic()
        deadline = start_time + self._timeout
        remaining = max(0.001, deadline - start_time)
        effective_read_timeout = min(self._read_timeout, remaining)

        request_timeout = httpx.Timeout(
            effective_read_timeout,
            connect=min(self._connect_timeout, effective_read_timeout),
            read=effective_read_timeout,
            write=effective_read_timeout,
        )

        try:
            res = client.post(url, json=payload, timeout=request_timeout)
        except httpx.ConnectTimeout as e:
            raise ProviderUnavailableError(
                provider=self.provider_name,
                url=self._base_url,
                reason=f"Connection timed out after {self._connect_timeout:.1f}s.",
            ) from e
        except httpx.ConnectError as e:
            raise ProviderUnavailableError(
                provider=self.provider_name,
                url=self._base_url,
                reason=str(e),
            ) from e
        except httpx.ReadTimeout as e:
            elapsed = time.monotonic() - start_time
            if time.monotonic() >= deadline or elapsed >= (self._timeout - 0.15):
                raise GenerationTimeoutError(
                    timeout=self._timeout,
                    provider=self.provider_name,
                    reason=f"Overall generation deadline ({self._timeout:.1f}s) exceeded",
                ) from e
            raise GenerationTimeoutError(
                timeout=self._read_timeout,
                provider=self.provider_name,
                reason=f"Read inactivity timeout after {self._read_timeout:.1f}s without response",
            ) from e
        except httpx.TimeoutException as e:
            raise GenerationTimeoutError(
                timeout=self._timeout,
                provider=self.provider_name,
                reason="Generation timeout",
            ) from e

        # Check overall monotonic deadline
        elapsed = time.monotonic() - start_time
        if time.monotonic() > deadline:
            raise GenerationTimeoutError(
                timeout=self._timeout,
                provider=self.provider_name,
                reason=f"Overall generation deadline ({self._timeout:.1f}s) exceeded",
            )

        if res.status_code == 404:
            raise ModelNotFoundError(
                model=self._model,
                provider=self.provider_name,
                install_command=f"ollama pull {self._model}",
            )
        elif res.status_code != 200:
            raise ProviderError(
                f"Ollama generation failed with status {res.status_code}: {res.text}"
            )

        try:
            data = res.json()
        except json.JSONDecodeError as e:
            raise ProviderProtocolError(f"Invalid JSON response from Ollama: {e}") from e

        if not isinstance(data, dict):
            raise ProviderProtocolError(f"Expected JSON object from Ollama, got {type(data).__name__}")

        if "error" in data:
            raise ProviderError(f"Ollama returned error: {data['error']}")

        response_text = str(data.get("response", "")).strip()
        if not response_text:
            raise IncompleteGenerationError("Ollama returned empty generation response.")

        total_duration = data.get("total_duration")
        duration_sec = (total_duration / 1e9) if total_duration else elapsed

        return GenerationResponse(
            text=response_text,
            model=self._model,
            total_tokens=data.get("eval_count"),
            prompt_tokens=data.get("prompt_eval_count"),
            duration_seconds=duration_sec,
            prompt_eval_count=data.get("prompt_eval_count"),
            eval_count=data.get("eval_count"),
            total_duration_ns=total_duration,
            load_duration_ns=data.get("load_duration"),
            prompt_eval_duration_ns=data.get("prompt_eval_duration"),
            eval_duration_ns=data.get("eval_duration"),
        )

    def stream(self, request: GenerationRequest) -> Generator[StreamChunk, None, None]:
        """Stream generated text chunks incrementally with strict NDJSON protocol verification."""
        client = self._get_client()
        payload = self._build_payload(request, stream=True)
        url = f"{self._base_url}/api/generate"
        start_time = time.monotonic()
        deadline = start_time + self._timeout
        remaining = max(0.001, deadline - start_time)
        effective_read_timeout = min(self._read_timeout, remaining)

        request_timeout = httpx.Timeout(
            effective_read_timeout,
            connect=min(self._connect_timeout, effective_read_timeout),
            read=effective_read_timeout,
            write=effective_read_timeout,
        )

        has_done = False
        total_text_parts: list[str] = []

        try:
            with client.stream("POST", url, json=payload, timeout=request_timeout) as response:
                if response.status_code == 404:
                    raise ModelNotFoundError(
                        model=self._model,
                        provider=self.provider_name,
                        install_command=f"ollama pull {self._model}",
                    )
                elif response.status_code != 200:
                    err_body = response.read().decode("utf-8", errors="replace")
                    raise ProviderError(
                        f"Ollama streaming failed with status {response.status_code}: {err_body}"
                    )

                for line in response.iter_lines():
                    clean_line = line.strip()
                    # 1. Ignore blank NDJSON lines
                    if not clean_line:
                        continue

                    # 2. Check monotonic deadline
                    if time.monotonic() > deadline:
                        raise GenerationTimeoutError(
                            timeout=self._timeout,
                            provider=self.provider_name,
                            reason=f"Overall generation deadline ({self._timeout:.1f}s) exceeded",
                        )

                    # 3. Reject malformed non-empty NDJSON records
                    try:
                        chunk_data = json.loads(clean_line)
                    except json.JSONDecodeError as e:
                        raise ProviderProtocolError(
                            f"Malformed NDJSON line received from Ollama: {clean_line!r}"
                        ) from e

                    if not isinstance(chunk_data, dict):
                        raise ProviderProtocolError(
                            f"Expected JSON object in stream line, got {type(chunk_data).__name__}: {clean_line!r}"
                        )

                    if "error" in chunk_data:
                        raise ProviderError(f"Ollama stream error: {chunk_data['error']}")

                    chunk_text = chunk_data.get("response", "")
                    is_done = bool(chunk_data.get("done", False))
                    eval_count = chunk_data.get("eval_count")

                    if chunk_text:
                        total_text_parts.append(chunk_text)

                    yield StreamChunk(
                        text=chunk_text,
                        is_done=is_done,
                        eval_count=eval_count,
                        prompt_eval_count=chunk_data.get("prompt_eval_count"),
                        total_duration_ns=chunk_data.get("total_duration"),
                        load_duration_ns=chunk_data.get("load_duration"),
                        prompt_eval_duration_ns=chunk_data.get("prompt_eval_duration"),
                        eval_duration_ns=chunk_data.get("eval_duration"),
                    )

                    if is_done:
                        has_done = True
                        break

        except httpx.ConnectTimeout as e:
            raise ProviderUnavailableError(
                provider=self.provider_name,
                url=self._base_url,
                reason=f"Connection timed out after {self._connect_timeout:.1f}s.",
            ) from e
        except httpx.ConnectError as e:
            raise ProviderUnavailableError(
                provider=self.provider_name,
                url=self._base_url,
                reason=str(e),
            ) from e
        except httpx.ReadTimeout as e:
            elapsed = time.monotonic() - start_time
            if time.monotonic() >= deadline or elapsed >= (self._timeout - 0.15):
                raise GenerationTimeoutError(
                    timeout=self._timeout,
                    provider=self.provider_name,
                    reason=f"Overall generation deadline ({self._timeout:.1f}s) exceeded",
                ) from e
            raise GenerationTimeoutError(
                timeout=self._read_timeout,
                provider=self.provider_name,
                reason=f"Read inactivity timeout after {self._read_timeout:.1f}s without response chunk",
            ) from e
        except (httpx.RemoteProtocolError, httpx.ReadError) as e:
            raise IncompleteGenerationError(
                f"Server connection disrupted during streaming: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise GenerationTimeoutError(
                timeout=self._timeout,
                provider=self.provider_name,
                reason="Generation timeout",
            ) from e

        # 4. Require explicit final done: true record
        if not has_done:
            raise IncompleteGenerationError(
                "Ollama stream ended prematurely without explicit completion marker ('done': true)."
            )

        # 5. Reject empty generation results
        if not "".join(total_text_parts).strip():
            raise IncompleteGenerationError(
                "Ollama completed stream but generated empty content."
            )
