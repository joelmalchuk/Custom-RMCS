from decimal import Decimal

from custom_rmcs.rma import build_adjustments


def test_rma_against_split_invoice_collapses_to_one_pob_adjustment(
    simple_credit_memo,
):
    """The RMA path uses only the OM-ref DFFs on each credit-memo line --
    no lineage map is consulted."""
    adjustments = build_adjustments([simple_credit_memo])

    assert len(adjustments) == 1
    adj = adjustments[0]
    assert adj.adjusts_document_number == "SD-OM-1001"
    assert len(adj.lines) == 1

    pob = adj.lines[0].performance_obligation
    assert pob.allocated_amount == Decimal("-1000.00")
    assert pob.customer_amount == Decimal("-200.00")
    assert pob.insurance_amount == Decimal("-800.00")
    assert pob.quantity == Decimal("-1")
    assert pob.om_order_number == "OM-1001"
    assert pob.om_line_number == "1"
