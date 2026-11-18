"""Knowledge graph utilities for BRENDA."""

from src.kg.builder import build_kg
from src.kg.retrieval import KGReader

__all__ = ["KGReader", "build_kg"]
