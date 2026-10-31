from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PreviewColumn(BaseModel):
    index: int
    title: str


class GroupParseResponse(BaseModel):
    rows: list[list[str]]
    header_row: int
    columns: list[PreviewColumn]
    data_rows_count: int


class GroupColumn(BaseModel):
    key: str
    title: str


class StudentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    data: dict[str, str]


class GroupListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    course: int
    students_count: int
    updated_at: datetime


class GroupDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    course: int
    columns: list[GroupColumn]
    students: list[StudentItem]
    created_at: datetime
    updated_at: datetime


class GroupUpdateRequest(BaseModel):
    number: str | None = Field(default=None, max_length=200)
    course: int | None = Field(default=None, ge=1, le=6)
    columns_order: list[str] | None = None

    @field_validator("number", mode="after")
    @classmethod
    def validate_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not (1 <= len(trimmed) <= 50):
            raise ValueError("Group number must be between 1 and 50 characters")
        return trimmed


class StudentCreateRequest(BaseModel):
    data: dict[str, Any]


class StudentCellUpdateRequest(BaseModel):
    key: str = Field(min_length=1)
    value: str

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("Value must be a string")
        trimmed = value.strip()
        if len(trimmed) > 500:
            raise ValueError("Value must be at most 500 characters")
        return trimmed
