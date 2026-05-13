"""Common Pydantic types used across routers."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(..., description="Total matching rows (before pagination)")
    page: int = Field(..., ge=1)
    per_page: int = Field(..., ge=1, le=200)
    pages: int = Field(..., ge=0, description="Total pages")
