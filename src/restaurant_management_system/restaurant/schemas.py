import re

from pydantic import BaseModel, Field, field_validator

GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


class DetailsIn(BaseModel):
    """What is printed on receipts besides the restaurant name (which has its own endpoint)."""

    address: str = Field(default="", max_length=300)
    phone: str = Field(default="", max_length=20)
    gstin: str = Field(default="", max_length=15)
    fssai: str = Field(default="", max_length=14)
    receipt_footer: str = Field(default="", max_length=200)

    @field_validator("gstin")
    @classmethod
    def check_gstin(cls, value: str) -> str:
        value = value.strip().upper()
        if value and not GSTIN_PATTERN.match(value):
            raise ValueError("GSTIN must be 15 characters, like 07AAAAA0000A1Z5")
        return value

    @field_validator("fssai")
    @classmethod
    def check_fssai(cls, value: str) -> str:
        value = value.strip()
        if value and not re.fullmatch(r"\d{14}", value):
            raise ValueError("FSSAI licence number must be 14 digits")
        return value

    @field_validator("address", "phone", "receipt_footer")
    @classmethod
    def strip(cls, value: str) -> str:
        return value.strip()


class DetailsOut(DetailsIn):
    name: str | None = None
    model_config = {"from_attributes": True}
