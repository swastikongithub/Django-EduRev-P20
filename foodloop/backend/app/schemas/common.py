import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _clean_indian_phone(value: str) -> str:
    digits = re.sub(r"[\s\-()]", "", value)
    digits = digits.removeprefix("+91").removeprefix("0091")
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"[6-9][0-9]{9}", digits):
        raise ValueError("Enter a 10-digit Indian mobile number.")
    return digits


Phone = Annotated[str, AfterValidator(_clean_indian_phone)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
