"""Provider-independent generation contract."""

from abc import ABC, abstractmethod
from collections.abc import Generator

from commit_cli.models import GenerationRequest, GenerationResponse, StreamChunk


class BaseLLMProvider(ABC):
    """Abstract interface for LLM text generation providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'Ollama')."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Active model identifier."""

    @abstractmethod
    def check_availability(self) -> bool:
        """Check if the provider service is running and reachable."""

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Execute non-streaming text generation."""

    @abstractmethod
    def stream(self, request: GenerationRequest) -> Generator[StreamChunk, None, None]:
        """Stream generated text chunks incrementally."""

    def get_context_window(self) -> int | None:
        """Return the model's maximum context window in tokens, or None if unknown."""
        return None

    def get_diagnostics(self) -> Any:
        """Return detailed provider and model diagnostics, or None if unsupported."""
        return None

    def close(self) -> None:
        """Release underlying provider resources (e.g. HTTP connections). Optional."""
