import pytest

from app import calculate_emi, format_inr, tenure_label


def test_emi_matches_hand_calculation():
    # 30,00,000 at 8.5% for 240 months -> r = 0.085/12, EMI ~ 26,034.70
    result = calculate_emi(3_000_000, 8.5, 240)
    assert result["emi"] == pytest.approx(26034.70, abs=0.5)
    assert result["total_payable"] == pytest.approx(result["emi"] * 240, abs=0.01)
    assert result["total_interest"] == pytest.approx(result["total_payable"] - 3_000_000, abs=0.01)


def test_emi_zero_rate_is_simple_division():
    result = calculate_emi(120_000, 0, 12)
    assert result["emi"] == pytest.approx(10_000)
    assert result["total_interest"] == pytest.approx(0)


@pytest.mark.parametrize("principal, rate, months", [(0, 8, 12), (-5, 8, 12), (1000, -1, 12), (1000, 8, 0)])
def test_emi_rejects_invalid_input(principal, rate, months):
    with pytest.raises(ValueError):
        calculate_emi(principal, rate, months)


def test_format_inr_uses_indian_grouping():
    assert format_inr(3000000) == "₹30,00,000"
    assert format_inr(999) == "₹999"
    assert format_inr(125000.5, 2) == "₹1,25,000.50"
    assert format_inr(None) == "₹0"


def test_tenure_label():
    assert tenure_label(240) == "20 yrs"
    assert tenure_label(18) == "1 yr 6 mos"
    assert tenure_label(6) == "6 mos"
