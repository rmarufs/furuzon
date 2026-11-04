from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MaterialItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course: int
    original_name: str
    size_bytes: int
    content_type: str
    public_token: str
    public_url: str
    group_ids: list[int]
    created_at: datetime
    updated_at: datetime


class MaterialGroupNode(BaseModel):
    id: int
    number: str
    files: list[MaterialItem]


class MaterialCourseNode(BaseModel):
    course: int
    groups: list[MaterialGroupNode]


class MaterialTreeResponse(BaseModel):
    courses: list[MaterialCourseNode]
