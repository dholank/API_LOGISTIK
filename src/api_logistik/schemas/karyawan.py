from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

Identifier = Annotated[str, Field(strict=True, pattern=r"^[0-9]{1,5}$")]


class KaryawanFields(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    nama: Annotated[str, Field(strict=True, min_length=1, max_length=50)]
    cabang: Annotated[str, Field(strict=True, min_length=1, max_length=30)]
    no_telp: Annotated[str, Field(strict=True, pattern=r"^[0-9]{1,20}$")]
    status: Annotated[str, Field(strict=True, min_length=1, max_length=10)]

    @field_validator("nama", "cabang", "status")
    @classmethod
    def validate_utf8_bytes(cls, value: str, info: ValidationInfo) -> str:
        limits = {"nama": 50, "cabang": 30, "status": 10}
        assert info.field_name is not None
        if len(value.encode("utf-8")) > limits[info.field_name]:
            raise ValueError("Field exceeds Oracle UTF-8 byte limit")
        return value

    @field_validator("nama", "cabang", "status", mode="before")
    @classmethod
    def strip_business_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CreateKaryawan(KaryawanFields):
    id_karyawan: Identifier


class UpdateKaryawan(KaryawanFields):
    pass


class KaryawanData(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    id_karyawan: Identifier
    nama: str | None = None
    cabang: str | None = None
    no_telp: str | None = None
    status: str | None = None

    @field_validator("id_karyawan", mode="before")
    @classmethod
    def normalize_identifier(cls, value: object) -> object:
        if type(value) is int and 0 <= value <= 99999:
            return str(value)
        if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 5:
            return str(int(value))
        return value
