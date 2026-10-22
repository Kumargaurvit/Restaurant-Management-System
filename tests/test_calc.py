from decimal import Decimal

import pytest

from restaurant_management_system.billing.calc import DiscountTooLargeError, Line, compute_bill

D = Decimal


def test_simple_bill_with_five_percent_gst() -> None:
    totals = compute_bill([Line(D("100.00"), 2, D("5"))])

    assert totals.subtotal == D("200.00")
    assert totals.cgst == D("5.00")
    assert totals.sgst == D("5.00")
    assert totals.round_off == D("0.00")
    assert totals.total == D("210.00")


def test_mixed_gst_rates() -> None:
    totals = compute_bill([Line(D("200.00"), 1, D("5")), Line(D("50.00"), 1, D("18"))])

    # tax = 10 + 9 = 19, so cgst 9.50 and sgst 9.50, total 269
    assert totals.cgst == D("9.50")
    assert totals.sgst == D("9.50")
    assert totals.total == D("269.00")


def test_discount_reduces_tax_proportionally() -> None:
    totals = compute_bill([Line(D("100.00"), 2, D("5"))], discount=D("20"))

    # taxable 180, tax 9.00
    assert totals.discount == D("20.00")
    assert totals.cgst + totals.sgst == D("9.00")
    assert totals.total == D("189.00")


def test_total_is_rounded_to_the_rupee_and_round_off_is_reported() -> None:
    totals = compute_bill([Line(D("99.99"), 1, D("5"))])

    # 99.99 + 5.00 = 104.99 -> 105
    assert totals.total == D("105.00")
    assert totals.round_off == D("0.01")


def test_round_off_can_be_negative() -> None:
    totals = compute_bill([Line(D("100.40"), 1, D("0"))])

    assert totals.total == D("100.00")
    assert totals.round_off == D("-0.40")


def test_cgst_plus_sgst_always_equals_total_tax() -> None:
    totals = compute_bill([Line(D("1.00"), 1, D("5"))])  # tax 0.05

    assert totals.cgst + totals.sgst == D("0.05")


def test_discount_larger_than_subtotal_is_rejected() -> None:
    with pytest.raises(DiscountTooLargeError):
        compute_bill([Line(D("100.00"), 1, D("5"))], discount=D("100.01"))


def test_full_discount_gives_zero_total() -> None:
    totals = compute_bill([Line(D("100.00"), 1, D("5"))], discount=D("100"))

    assert totals.total == D("0.00")
    assert totals.cgst == D("0.00")


def test_empty_bill_is_zero() -> None:
    totals = compute_bill([])

    assert totals.total == D("0.00")
