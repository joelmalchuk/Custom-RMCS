"""FBDI column schema for the RMCS *Import Customer Contract Source Data* template.

Oracle revises FBDI column lists across releases. The lists below are the
columns this scaffold writes; verify them against the template downloaded
from your tenant (Setup and Maintenance -> File-Based Data Import for
Oracle Financials Cloud -> *Customer Contract Source Data Import*) before
go-live, and add/remove columns here as needed. All rows are written with
empty strings for columns whose values are not produced by the pipeline.

The order of the tuples below is the order columns appear in the CSV --
FBDI relies on positional columns, not headers, but we write headers as the
first row for human readability. The import loader ignores header rows that
start with a `#` character, which is what we use.
"""

from __future__ import annotations


SOURCE_DOCUMENTS_COLUMNS: tuple[str, ...] = (
    "SOURCE_SYSTEM_CODE",
    "SOURCE_DOCUMENT_TYPE_CODE",
    "SOURCE_DOCUMENT_NUMBER",
    "CONTRACT_IDENTIFIER",
    "CUSTOMER_ACCOUNT_NUMBER",
    "BUSINESS_UNIT_NAME",
    "DOCUMENT_DATE",
    "CURRENCY_CODE",
    "IS_CONTRACT_MODIFICATION_FLAG",
    "MODIFIES_SOURCE_DOCUMENT_NUMBER",
)


SOURCE_DOC_LINES_COLUMNS: tuple[str, ...] = (
    "SOURCE_SYSTEM_CODE",
    "SOURCE_DOCUMENT_NUMBER",
    "SOURCE_DOCUMENT_LINE_NUMBER",
    "ITEM_NUMBER",
    "ITEM_CLASS",
    "QUANTITY",
    "LIST_PRICE",
    "SSP_PER_UNIT",
    "ALLOCATED_AMOUNT",
    "FULFILLMENT_DATE",
    "OM_ORDER_NUMBER",
    "OM_LINE_NUMBER",
    "CUSTOMER_PAY_AMOUNT",
    "INSURANCE_PAY_AMOUNT",
)


SOURCE_DOC_SUB_LINES_COLUMNS: tuple[str, ...] = (
    "SOURCE_SYSTEM_CODE",
    "SOURCE_DOCUMENT_NUMBER",
    "SOURCE_DOCUMENT_LINE_NUMBER",
    "SUB_LINE_NUMBER",
    "BILLING_PARTY_TYPE",
    "AMOUNT",
)
