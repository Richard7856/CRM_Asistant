from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def create(cls, items: list, total: int, params: PaginationParams) -> "PaginatedResponse":
        return cls(
            items=items,
            total=total,
            page=params.page,
            size=params.size,
            pages=(total + params.size - 1) // params.size if total > 0 else 0,
        )
