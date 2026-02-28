"""Abstract base classes for file system repositories."""

import abc
from typing import Any


class AbstractFileRepository(abc.ABC):
    """Abstract interface for file system repositories."""
    
    @abc.abstractmethod
    def load(self, path: str) -> dict[str, Any] | Any:
        """Load data from a file."""
        pass

    @abc.abstractmethod
    def save(self, path: str, data: Any) -> None:
        """Save data to a file."""
        pass
