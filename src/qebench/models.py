"""Pydantic models for benchmark dataset entries.

These models define the schema for terms, sentences, and paragraphs.
Use `Term.model_json_schema()` etc. to generate JSON Schema for CI validation.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Difficulty(StrEnum):
    basic = "basic"
    intermediate = "intermediate"
    advanced = "advanced"


class HumanScores(BaseModel):
    accuracy: int = Field(ge=1, le=10)
    fluency: int = Field(ge=1, le=10)


class TermContext(BaseModel):
    """A sentence from a lecture that uses a term in context."""

    text: str = Field(min_length=1, description="Sentence containing the term")
    source: str = Field(default="", description="Lecture source path in repo, e.g. lecture-python-intro/intro.md")


class Term(BaseModel):
    id: str = Field(pattern=r"^term-\d{3,}$", description="Unique term ID, e.g. term-001")
    en: str = Field(min_length=1, description="English term")
    zh: str = Field(min_length=1, description="Chinese translation")
    domain: str = Field(min_length=1, description="Subject domain, e.g. dynamic-programming")
    difficulty: Difficulty
    alternatives: list[str] = Field(default_factory=list, description="Alternative valid translations")
    contexts: list[TermContext] = Field(default_factory=list, description="Example sentences showing usage")
    source: str = Field(default="", description="Origin reference, e.g. quantecon/dp-intro")


class Sentence(BaseModel):
    id: str = Field(pattern=r"^sent-\d{3,}$", description="Unique sentence ID, e.g. sent-042")
    en: str = Field(min_length=1)
    zh: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    difficulty: Difficulty
    key_terms: list[str] = Field(default_factory=list, description="Related term IDs")
    human_scores: HumanScores | None = None
    source: str = ""


class Paragraph(BaseModel):
    id: str = Field(pattern=r"^para-\d{3,}$", description="Unique paragraph ID, e.g. para-007")
    en: str = Field(min_length=1)
    zh: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    difficulty: Difficulty
    key_terms: list[str] = Field(default_factory=list)
    contains_math: bool = False
    contains_code: bool = False
    human_scores: HumanScores | None = None
    source: str = ""


class DataFile(BaseModel):
    """Wrapper for a JSON data file containing a list of entries."""

    version: str = "1.0"
    entries: list[Term] | list[Sentence] | list[Paragraph]
