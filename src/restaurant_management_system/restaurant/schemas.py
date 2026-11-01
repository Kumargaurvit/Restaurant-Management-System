import base64
import binascii
import re

from pydantic import BaseModel, Field, field_validator

GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

MAX_LOGO_BYTES = 100_000
# Raster images only (an SVG can carry scripts). The first bytes must really match the type.
LOGO_TYPES = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpeg": (b"\xff\xd8\xff",),
    "webp": (b"RIFF",),
}
LOGO_PATTERN = re.compile(r"^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/]+=*)$")


class DetailsIn(BaseModel):
    """What is printed on receipts besides the restaurant name (which has its own endpoint)."""

    address: str = Field(default="", max_length=300)
    phone: str = Field(default="", max_length=20)
    gstin: str = Field(default="", max_length=15)
    fssai: str = Field(default="", max_length=14)
    receipt_footer: str = Field(default="", max_length=200)
    # A small image as a data URL. Empty removes the logo.
    logo: str = Field(default="", max_length=150_000)

    @field_validator("logo")
    @classmethod
    def check_logo(cls, value: str) -> str:
        if not value:
            return ""
        match = LOGO_PATTERN.match(value)
        if match is None:
            raise ValueError("The logo must be a PNG, JPEG or WebP image")
        kind = match.group(1)
        try:
            data = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("The logo image is corrupt") from None
        if len(data) > MAX_LOGO_BYTES:
            raise ValueError("The logo is too large. Use an image under 100 KB")
        if not data.startswith(LOGO_TYPES[kind]) or (kind == "webp" and data[8:12] != b"WEBP"):
            raise ValueError("The logo file does not match its image type")
        return value

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
