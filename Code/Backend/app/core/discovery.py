"""Shared labels and recurring weekly windows; never infer personal location."""
import unicodedata
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

WEEK_MINUTES = 7 * 24 * 60


def normalized_label(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


class AvailabilityWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    weekday: int = Field(ge=0, le=6)
    start_minute: int = Field(ge=0, le=1439)
    end_minute: int = Field(ge=1, le=1440)

    @model_validator(mode="after")
    def increasing(self):
        if self.end_minute <= self.start_minute:
            raise ValueError("End must be after start; split overnight windows across adjacent days.")
        return self


def weekly_intervals(windows: Sequence[dict | AvailabilityWindow]) -> list[tuple[int, int]]:
    ranges = []
    for raw in windows:
        row = raw if isinstance(raw, AvailabilityWindow) else AvailabilityWindow.model_validate(raw)
        ranges.append((row.weekday * 1440 + row.start_minute, row.weekday * 1440 + row.end_minute))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged
