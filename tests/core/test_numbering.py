import pytest

from insurance_core.issuance.numbering import is_well_formed, luhn_check_digit, make_policy_number


def test_matches_the_number_issued_in_colab():
    assert make_policy_number("HCN", 2026, 1) == "NGI-HCN-2026-000001-1"


def test_known_luhn_value():
    assert luhn_check_digit("7992739871") == 3       # the textbook Luhn example


@pytest.mark.parametrize("seq", [1, 42, 999, 123456])
def test_every_single_digit_typo_is_caught(seq):
    number = make_policy_number("HMC", 2026, seq)
    assert is_well_formed(number)
    prefix, product, year, digits, check = number.split("-")
    body = year + digits
    for position in range(len(body)):
        for wrong in "0123456789":
            if wrong == body[position]:
                continue
            typo = body[:position] + wrong + body[position + 1:]
            assert not is_well_formed(f"{prefix}-{product}-{typo[:4]}-{typo[4:]}-{check}")


@pytest.mark.parametrize("bad", ["", "NGI-HCN-2026-000001", "NGI-HCN-20X6-000001-1", "NGI-HCN-2026-000001-12",
                                 "not a policy number"])
def test_malformed_numbers_are_rejected_without_crashing(bad):
    assert not is_well_formed(bad)