from __future__ import annotations

import re

_NIF_DNI = re.compile(r"^\d{8}[A-Z]$")
_NIF_CIF = re.compile(r"^[A-HJNPQRSUVW]\d{7}[0-9A-J]$")
_NIF_NIE = re.compile(r"^[XYZ]\d{7}[A-Z]$")

_DNI_CONTROL_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_NIE_PREFIX_DIGIT = {"X": "0", "Y": "1", "Z": "2"}

# CIF organisation-type letters where the control character must be a digit,
# must be a letter, or may legally be either (per AEAT's spec).
_CIF_DIGIT_ONLY_ORG_LETTERS = set("ABEH")
_CIF_LETTER_ONLY_ORG_LETTERS = set("KPQS")
_CIF_CONTROL_LETTERS = "JABCDEFGHI"


def _dni_control_letter(number: int) -> str:
    return _DNI_CONTROL_LETTERS[number % 23]


def _is_valid_dni(n: str) -> bool:
    return n[8] == _dni_control_letter(int(n[:8]))


def _is_valid_nie(n: str) -> bool:
    number = int(_NIE_PREFIX_DIGIT[n[0]] + n[1:8])
    return n[8] == _dni_control_letter(number)


def _cif_control_digit(digits: str) -> int:
    even_sum = 0
    odd_doubled_sum = 0
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == 0:  # 0-indexed even -> 1-indexed odd position (1,3,5,7)
            doubled = d * 2
            odd_doubled_sum += doubled - 9 if doubled > 9 else doubled
        else:
            even_sum += d
    total = even_sum + odd_doubled_sum
    return (10 - (total % 10)) % 10


def _is_valid_cif(n: str) -> bool:
    org_letter, digits, control = n[0], n[1:8], n[8]
    control_digit = _cif_control_digit(digits)
    if org_letter in _CIF_DIGIT_ONLY_ORG_LETTERS:
        return control == str(control_digit)
    if org_letter in _CIF_LETTER_ONLY_ORG_LETTERS:
        return control == _CIF_CONTROL_LETTERS[control_digit]
    return control == str(control_digit) or control == _CIF_CONTROL_LETTERS[control_digit]


def is_valid_nif(nif: str) -> bool:
    """Format AND control-digit/letter check for Spanish DNI, NIE and CIF."""
    n = nif.strip().upper()
    if _NIF_DNI.match(n):
        return _is_valid_dni(n)
    if _NIF_NIE.match(n):
        return _is_valid_nie(n)
    if _NIF_CIF.match(n):
        return _is_valid_cif(n)
    return False
