from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")
RUPEE = Decimal("1")


class DiscountTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class Line:
    unit_price: Decimal
    quantity: int
    gst_rate: Decimal


@dataclass(frozen=True)
class BillTotals:
    subtotal: Decimal
    discount: Decimal
    cgst: Decimal
    sgst: Decimal
    round_off: Decimal
    total: Decimal


def _money(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def compute_bill(lines: Sequence[Line], discount: Decimal = Decimal("0")) -> BillTotals:
    """Totals for a bill.

    Prices are GST-exclusive. The discount is taken off the subtotal before tax, so tax is
    scaled down by the same proportion. Intrastate supply: tax is split evenly into CGST and
    SGST. The total is rounded to the nearest rupee and the difference is reported as round_off.
    """
    discount = _money(discount)
    subtotal = _money(sum((line.unit_price * line.quantity for line in lines), Decimal("0")))
    if discount < 0 or discount > subtotal:
        raise DiscountTooLargeError("Discount must be between 0 and the subtotal")

    line_tax = sum(
        (line.unit_price * line.quantity * line.gst_rate / 100 for line in lines), Decimal("0")
    )
    if subtotal > 0:
        tax = _money(line_tax * (subtotal - discount) / subtotal)
    else:
        tax = Decimal("0.00")

    cgst = _money(tax / 2)
    sgst = tax - cgst
    raw_total = subtotal - discount + tax
    total = raw_total.quantize(RUPEE, rounding=ROUND_HALF_UP)
    return BillTotals(
        subtotal=subtotal,
        discount=discount,
        cgst=cgst,
        sgst=sgst,
        round_off=_money(total - raw_total),
        total=_money(total),
    )
