"""Abstract repository base class."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class AbstractRepository(ABC, Generic[T]):
    """Generic ABC for CRUD repositories."""

    @abstractmethod
    async def get_by_id(self, id: str) -> T | None:
        """Retrieve an entity by its ID."""
        ...

    @abstractmethod
    async def save(self, entity: T) -> T:
        """Save (create or update) an entity."""
        ...

    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Delete an entity by its ID. Returns True if deleted."""
        ...

    @abstractmethod
    async def list_all(self) -> list[T]:
        """List all entities."""
        ...
