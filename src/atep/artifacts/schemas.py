import re
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from atep.artifacts.models import TestArtifact

ARTIFACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$")
SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,254}$")


class ArtifactKind(StrEnum):
    LOG = "log"
    REPORT = "report"
    TRACE = "trace"
    IMAGE = "image"
    VIDEO = "video"
    BINARY = "binary"
    OTHER = "other"


class ArtifactCreate(BaseModel):
    artifact_id: str = Field(min_length=8, max_length=64)
    kind: ArtifactKind
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=120)

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        value = value.strip()
        if not ARTIFACT_ID_PATTERN.fullmatch(value):
            raise ValueError("artifact IDs must be URL-safe and contain 8 to 64 characters")
        return value

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        value = value.strip()
        if not SAFE_FILENAME_PATTERN.fullmatch(value) or value in {".", ".."}:
            raise ValueError("filenames must be portable and must not contain path separators")
        return value

    @field_validator("media_type")
    @classmethod
    def normalize_media_type(cls, value: str) -> str:
        value = value.strip().casefold()
        if any(character.isspace() or ord(character) < 32 for character in value):
            raise ValueError("media types must not contain whitespace or control characters")
        return value


class ArtifactResponse(BaseModel):
    id: UUID
    artifact_id: str
    run_id: str
    uploaded_by_user_id: UUID
    kind: ArtifactKind
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class ArtifactPage(BaseModel):
    items: list[ArtifactResponse]
    total: int
    limit: int
    offset: int


def artifact_response(artifact: "TestArtifact", run_id: str) -> ArtifactResponse:
    return ArtifactResponse(
        id=artifact.id,
        artifact_id=artifact.artifact_id,
        run_id=run_id,
        uploaded_by_user_id=artifact.uploaded_by_user_id,
        kind=artifact.kind,
        filename=artifact.filename,
        media_type=artifact.media_type,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
        created_at=artifact.created_at,
    )
