from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ActivityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    object_type: str
    object_id: int | None
    object_title: str
    created_at: datetime
