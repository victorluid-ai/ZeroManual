from __future__ import annotations

from apps.common.tax_id import is_valid_nif


def test_valid_dni_with_correct_control_letter() -> None:
    assert is_valid_nif("12345678Z")


def test_dni_with_wrong_control_letter_rejected() -> None:
    assert not is_valid_nif("12345678A")


def test_valid_nie() -> None:
    assert is_valid_nif("X1234567L")


def test_nie_with_wrong_control_letter_rejected() -> None:
    assert not is_valid_nif("X1234567A")


def test_valid_cif_digit_only_org_letter() -> None:
    # 'A' is a digit-only-control org letter (e.g. Telefonica's real CIF).
    assert is_valid_nif("A58818501")


def test_cif_with_wrong_control_digit_rejected() -> None:
    assert not is_valid_nif("B12345678")


def test_valid_cif_computed() -> None:
    assert is_valid_nif("B12345674")


def test_malformed_input_rejected() -> None:
    assert not is_valid_nif("not-a-nif")
    assert not is_valid_nif("")
