import re
from typing import Any


def clean_name(value: Any) -> str:
    if value is None:
        return ""

    value = str(value).strip()

    if not value:
        return ""

    return " ".join(
        word.capitalize()
        for word in value.split()
    )


def clean_email(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip().lower()


def clean_phone(value: Any) -> str:
    if value is None:
        return ""

    return re.sub(
        r"\D",
        "",
        str(value).strip()
    )


def clean_address(
    value: Any,
    reference_map: dict[str, str] | None = None
) -> str:

    if value is None:
        return ""

    text = str(value).strip().lower()

    for short_form, long_form in (reference_map or {}).items():
        text = text.replace(
            short_form,
            long_form
        )

    text = re.sub(r"\s+", " ", text)

    return text.strip()