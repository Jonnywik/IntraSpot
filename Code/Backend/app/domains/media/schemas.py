from pydantic import BaseModel


class MediaMutationOut(BaseModel):
    media_url: str | None
    width: int | None
    height: int | None
    byte_size: int | None
    draft_version: str | None
