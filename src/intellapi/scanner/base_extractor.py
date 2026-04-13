"""Abstract base extractor interface.

All framework-specific extractors implement this interface, producing
an IntermediateRepresentation from a list of source files.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from intellapi.scanner.ir import IntermediateRepresentation


class BaseExtractor(ABC):
    """Abstract extractor that all framework-specific extractors implement."""

    @abstractmethod
    def extract(self, files: list[Path]) -> IntermediateRepresentation:
        """Analyze source files and produce an IntermediateRepresentation.

        Args:
            files: List of source file paths to analyze.

        Returns:
            IntermediateRepresentation with extracted endpoints, models, etc.
        """
        ...

    @property
    @abstractmethod
    def framework_name(self) -> str:
        """Human-readable framework name (e.g., 'FastAPI', 'Express')."""
        ...

    @property
    @abstractmethod
    def language(self) -> str:
        """Language this extractor handles ('python', 'javascript', 'typescript')."""
        ...
