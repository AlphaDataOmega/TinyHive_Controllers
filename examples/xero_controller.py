"""
Xero Controller for TinyHive

A controller for the Xero Accounting API providing integration with
invoices, contacts, accounts, payments, and organisation details.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "tenant_id": "your-xero-tenant-id",
    "token_env": "XERO_ACCESS_TOKEN"
}

Authentication:
--------------
Xero uses OAuth 2.0. You need to:
1. Create a Xero app at https://developer.xero.com
2. Obtain an access token via OAuth 2.0 flow
3. Set the token in the environment variable specified by token_env
4. The tenant_id is obtained from the /connections endpoint after auth

Required Scopes:
---------------
- accounting.transactions (invoices, payments)
- accounting.contacts
- accounting.settings (accounts, organisation)

Dependencies:
------------
None (standard library only)

Method IDs:
----------
controller.xero.{profile}.list_invoices
controller.xero.{profile}.create_invoice
controller.xero.{profile}.get_invoice
controller.xero.{profile}.list_contacts
controller.xero.{profile}.create_contact
controller.xero.{profile}.list_accounts
controller.xero.{profile}.create_payment
controller.xero.{profile}.get_organisation
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.xero")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Xero API base URL
XERO_API_BASE = "https://api.xero.com/api.xro/2.0"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile from the profiles directory."""
    profile_path = PROFILES_DIR / f"{name}.json"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {name}")

    with open(profile_path) as f:
        return json.load(f)


def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get OAuth access token from environment variable."""
    token_env = profile.get("token_env", "XERO_ACCESS_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(
            f"Environment variable '{token_env}' not set. "
            "Obtain a token via Xero OAuth 2.0 flow."
        )
    return token


def _get_tenant_id(profile: Dict[str, Any]) -> str:
    """Get Xero tenant ID from profile."""
    tenant_id = profile.get("tenant_id")
    if not tenant_id:
        raise ValueError(
            "tenant_id not set in profile. "
            "Obtain tenant ID from Xero /connections endpoint."
        )
    return tenant_id


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    token: str,
    tenant_id: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Xero API call."""
    url = f"{XERO_API_BASE}/{endpoint}"

    if query_params:
        query_string = urlencode(query_params)
        url = f"{url}?{query_string}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Xero-tenant-id": tenant_id,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            # Xero returns errors in various formats
            if "Message" in error_data:
                error_message = error_data["Message"]
            elif "Detail" in error_data:
                error_message = error_data["Detail"]
            elif "Elements" in error_data:
                # Validation errors
                elements = error_data.get("Elements", [])
                errors = []
                for elem in elements:
                    for err in elem.get("ValidationErrors", []):
                        errors.append(err.get("Message", ""))
                error_message = "; ".join(errors) if errors else error_body[:500]
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Xero API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Xero API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Invoice Actions
# =============================================================================

def list_invoices(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List invoices.

    Params:
        where (str): Filter expression (e.g., "Status==\"DRAFT\"")
        order (str): Order by field (e.g., "Date DESC")
        page (int): Page number for pagination (default: 1)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    tenant_id = _get_tenant_id(profile)

    query_params = {}
    if params.get("where"):
        query_params["where"] = params["where"]
    if params.get("order"):
        query_params["order"] = params["order"]
    if params.get("page"):
        query_params["page"] = str(params["page"])

    result = _api_call(token, tenant_id, "Invoices", query_params=query_params)

    if result.get("ok") and "result" in result:
        invoices = result["result"].get("Invoices", [])
        return {
            "ok": True,
            "data": {
                "invoices": [
                    {
                        "invoice_id": inv.get("InvoiceID"),
                        "invoice_number": inv.get("InvoiceNumber"),
                        "type": inv.get("Type"),
                        "status": inv.get("Status"),
                        "contact_name": inv.get("Contact", {}).get("Name"),
                        "date": inv.get("Date"),
                        "due_date": inv.get("DueDate"),
                        "total": inv.get("Total"),
                        "amount_due": inv.get("AmountDue"),
                        "amount_paid": inv.get("AmountPaid"),
                        "currency_code": inv.get("CurrencyCode"),
                    }
                    for inv in invoices
                ],
                "count": len(invoices)
            }
        }
    return result


def create_invoice(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an invoice.

    Params:
        type (str): Invoice type - "ACCREC" (receivable) or "ACCPAY" (payable) (required)
        contact (dict): Contact info with ContactID or Name (required)
        line_items (list): List of line items (required)
            Each item: {description, quantity, unit_amount, account_code, tax_type}
        due_date (str): Due date in YYYY-MM-DD format (optional)
        date (str): Invoice date in YYYY-MM-DD format (optional)
        reference (str): Reference number (optional)
        status (str): Invoice status - "DRAFT", "SUBMITTED", "AUTHORISED" (default: DRAFT)
        currency_code (str): Currency code (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    tenant_id = _get_tenant_id(profile)

    inv_type = params.get("type")
    contact = params.get("contact")
    line_items = params.get("line_items")

    if not inv_type:
        return {"ok": False, "error": "type is required (ACCREC or ACCPAY)"}
    if not contact:
        return {"ok": False, "error": "contact is required"}
    if not line_items:
        return {"ok": False, "error": "line_items is required"}

    # Build contact object
    contact_obj = {}
    if isinstance(contact, dict):
        if contact.get("ContactID"):
            contact_obj["ContactID"] = contact["ContactID"]
        elif contact.get("Name"):
            contact_obj["Name"] = contact["Name"]
        else:
            return {"ok": False, "error": "contact must have ContactID or Name"}
    elif isinstance(contact, str):
        contact_obj["Name"] = contact
    else:
        return {"ok": False, "error": "contact must be dict or string"}

    # Build line items
    xero_line_items = []
    for item in line_items:
        line = {
            "Description": item.get("description", ""),
        }
        if "quantity" in item:
            line["Quantity"] = item["quantity"]
        if "unit_amount" in item:
            line["UnitAmount"] = item["unit_amount"]
        if "account_code" in item:
            line["AccountCode"] = item["account_code"]
        if "tax_type" in item:
            line["TaxType"] = item["tax_type"]
        if "line_amount" in item:
            line["LineAmount"] = item["line_amount"]
        xero_line_items.append(line)

    invoice_data = {
        "Type": inv_type,
        "Contact": contact_obj,
        "LineItems": xero_line_items,
    }

    if params.get("due_date"):
        invoice_data["DueDate"] = params["due_date"]
    if params.get("date"):
        invoice_data["Date"] = params["date"]
    if params.get("reference"):
        invoice_data["Reference"] = params["reference"]
    if params.get("status"):
        invoice_data["Status"] = params["status"]
    if params.get("currency_code"):
        invoice_data["CurrencyCode"] = params["currency_code"]

    result = _api_call(
        token, tenant_id, "Invoices",
        method="POST",
        data={"Invoices": [invoice_data]}
    )

    if result.get("ok") and "result" in result:
        invoices = result["result"].get("Invoices", [])
        if invoices:
            inv = invoices[0]
            return {
                "ok": True,
                "data": {
                    "invoice_id": inv.get("InvoiceID"),
                    "invoice_number": inv.get("InvoiceNumber"),
                    "type": inv.get("Type"),
                    "status": inv.get("Status"),
                    "total": inv.get("Total"),
                }
            }
    return result


def get_invoice(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a single invoice by ID.

    Params:
        invoice_id (str): The invoice ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    tenant_id = _get_tenant_id(profile)

    invoice_id = params.get("invoice_id")
    if not invoice_id:
        return {"ok": False, "error": "invoice_id is required"}

    result = _api_call(token, tenant_id, f"Invoices/{quote(invoice_id, safe='')}")

    if result.get("ok") and "result" in result:
        invoices = result["result"].get("Invoices", [])
        if invoices:
            inv = invoices[0]
            return {
                "ok": True,
                "data": {
                    "invoice_id": inv.get("InvoiceID"),
                    "invoice_number": inv.get("InvoiceNumber"),
                    "type": inv.get("Type"),
                    "status": inv.get("Status"),
                    "contact": {
                        "contact_id": inv.get("Contact", {}).get("ContactID"),
                        "name": inv.get("Contact", {}).get("Name"),
                    },
                    "date": inv.get("Date"),
                    "due_date": inv.get("DueDate"),
                    "line_items": [
                        {
                            "description": li.get("Description"),
                            "quantity": li.get("Quantity"),
                            "unit_amount": li.get("UnitAmount"),
                            "line_amount": li.get("LineAmount"),
                            "account_code": li.get("AccountCode"),
                            "tax_type": li.get("TaxType"),
                        }
                        for li in inv.get("LineItems", [])
                    ],
                    "sub_total": inv.get("SubTotal"),
                    "total_tax": inv.get("TotalTax"),
                    "total": inv.get("Total"),
                    "amount_due": inv.get("AmountDue"),
                    "amount_paid": inv.get("AmountPaid"),
                    "currency_code": inv.get("CurrencyCode"),
                    "reference": inv.get("Reference"),
                    "url": inv.get("Url"),
                }
            }
        return {"ok": False, "error": "Invoice not found"}
    return result


# =============================================================================
# Contact Actions
# =============================================================================

def list_contacts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List contacts.

    Params:
        where (str): Filter expression (e.g., "Name.StartsWith(\"A\")")
        order (str): Order by field (e.g., "Name ASC")
        page (int): Page number for pagination (default: 1)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    tenant_id = _get_tenant_id(profile)

    query_params = {}
    if params.get("where"):
        query_params["where"] = params["where"]
    if params.get("order"):
        query_params["order"] = params["order"]
    if params.get("page"):
        query_params["page"] = str(params["page"])

    result = _api_call(token, tenant_id, "Contacts", query_params=query_params)

    if result.get("ok") and "result" in result:
        contacts = result["result"].get("Contacts", [])
        return {
            "ok": True,
            "data": {
                "contacts": [
                    {
                        "contact_id": c.get("ContactID"),
                        "name": c.get("Name"),
                        "first_name": c.get("FirstName"),
                        "last_name": c.get("LastName"),
                        "email": c.get("EmailAddress"),
                        "is_supplier": c.get("IsSupplier"),
                        "is_customer": c.get("IsCustomer"),
                        "contact_status": c.get("ContactStatus"),
                    }
                    for c in contacts
                ],
                "count": len(contacts)
            }
        }
    return result


def create_contact(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a contact.

    Params:
        name (str): Contact name (required)
        email (str): Email address (optional)
        first_name (str): First name (optional)
        last_name (str): Last name (optional)
        phones (list): List of phone numbers (optional)
            Each: {type, number} where type is DEFAULT, DDI, MOBILE, FAX
        addresses (list): List of addresses (optional)
            Each: {type, address_line1, city, region, postal_code, country}
            where type is POBOX, STREET, DELIVERY
        is_supplier (bool): Is a supplier (optional)
        is_customer (bool): Is a customer (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    tenant_id = _get_tenant_id(profile)

    name = params.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}

    contact_data = {
        "Name": name,
    }

    if params.get("email"):
        contact_data["EmailAddress"] = params["email"]
    if params.get("first_name"):
        contact_data["FirstName"] = params["first_name"]
    if params.get("last_name"):
        contact_data["LastName"] = params["last_name"]
    if params.get("is_supplier") is not None:
        contact_data["IsSupplier"] = params["is_supplier"]
    if params.get("is_customer") is not None:
        contact_data["IsCustomer"] = params["is_customer"]

    # Build phones
    if params.get("phones"):
        xero_phones = []
        for phone in params["phones"]:
            xero_phones.append({
                "PhoneType": phone.get("type", "DEFAULT"),
                "PhoneNumber": phone.get("number", ""),
            })
        contact_data["Phones"] = xero_phones

    # Build addresses
    if params.get("addresses"):
        xero_addresses = []
        for addr in params["addresses"]:
            xero_addr = {
                "AddressType": addr.get("type", "STREET"),
            }
            if addr.get("address_line1"):
                xero_addr["AddressLine1"] = addr["address_line1"]
            if addr.get("address_line2"):
                xero_addr["AddressLine2"] = addr["address_line2"]
            if addr.get("city"):
                xero_addr["City"] = addr["city"]
            if addr.get("region"):
                xero_addr["Region"] = addr["region"]
            if addr.get("postal_code"):
                xero_addr["PostalCode"] = addr["postal_code"]
            if addr.get("country"):
                xero_addr["Country"] = addr["country"]
            xero_addresses.append(xero_addr)
        contact_data["Addresses"] = xero_addresses

    result = _api_call(
        token, tenant_id, "Contacts",
        method="POST",
        data={"Contacts": [contact_data]}
    )

    if result.get("ok") and "result" in result:
        contacts = result["result"].get("Contacts", [])
        if contacts:
            c = contacts[0]
            return {
                "ok": True,
                "data": {
                    "contact_id": c.get("ContactID"),
                    "name": c.get("Name"),
                    "email": c.get("EmailAddress"),
                    "contact_status": c.get("ContactStatus"),
                }
            }
    return result


# =============================================================================
# Account Actions
# =============================================================================

def list_accounts(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List chart of accounts.

    Params:
        where (str): Filter expression (e.g., "Type==\"REVENUE\"")
        order (str): Order by field (e.g., "Name ASC")
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    tenant_id = _get_tenant_id(profile)

    query_params = {}
    if params.get("where"):
        query_params["where"] = params["where"]
    if params.get("order"):
        query_params["order"] = params["order"]

    result = _api_call(token, tenant_id, "Accounts", query_params=query_params)

    if result.get("ok") and "result" in result:
        accounts = result["result"].get("Accounts", [])
        return {
            "ok": True,
            "data": {
                "accounts": [
                    {
                        "account_id": a.get("AccountID"),
                        "code": a.get("Code"),
                        "name": a.get("Name"),
                        "type": a.get("Type"),
                        "status": a.get("Status"),
                        "class": a.get("Class"),
                        "tax_type": a.get("TaxType"),
                        "description": a.get("Description"),
                        "enable_payments_to_account": a.get("EnablePaymentsToAccount"),
                    }
                    for a in accounts
                ],
                "count": len(accounts)
            }
        }
    return result


# =============================================================================
# Payment Actions
# =============================================================================

def create_payment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a payment against an invoice.

    Params:
        invoice (dict): Invoice reference with InvoiceID or InvoiceNumber (required)
        account (dict): Account reference with AccountID or Code (required)
        amount (float): Payment amount (required)
        date (str): Payment date in YYYY-MM-DD format (required)
        reference (str): Payment reference (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    tenant_id = _get_tenant_id(profile)

    invoice = params.get("invoice")
    account = params.get("account")
    amount = params.get("amount")
    date = params.get("date")

    if not invoice:
        return {"ok": False, "error": "invoice is required"}
    if not account:
        return {"ok": False, "error": "account is required"}
    if amount is None:
        return {"ok": False, "error": "amount is required"}
    if not date:
        return {"ok": False, "error": "date is required"}

    # Build invoice reference
    invoice_obj = {}
    if isinstance(invoice, dict):
        if invoice.get("InvoiceID"):
            invoice_obj["InvoiceID"] = invoice["InvoiceID"]
        elif invoice.get("invoice_id"):
            invoice_obj["InvoiceID"] = invoice["invoice_id"]
        elif invoice.get("InvoiceNumber"):
            invoice_obj["InvoiceNumber"] = invoice["InvoiceNumber"]
        elif invoice.get("invoice_number"):
            invoice_obj["InvoiceNumber"] = invoice["invoice_number"]
        else:
            return {"ok": False, "error": "invoice must have InvoiceID or InvoiceNumber"}
    elif isinstance(invoice, str):
        # Assume it's an invoice ID
        invoice_obj["InvoiceID"] = invoice
    else:
        return {"ok": False, "error": "invoice must be dict or string"}

    # Build account reference
    account_obj = {}
    if isinstance(account, dict):
        if account.get("AccountID"):
            account_obj["AccountID"] = account["AccountID"]
        elif account.get("account_id"):
            account_obj["AccountID"] = account["account_id"]
        elif account.get("Code"):
            account_obj["Code"] = account["Code"]
        elif account.get("code"):
            account_obj["Code"] = account["code"]
        else:
            return {"ok": False, "error": "account must have AccountID or Code"}
    elif isinstance(account, str):
        # Assume it's an account code
        account_obj["Code"] = account
    else:
        return {"ok": False, "error": "account must be dict or string"}

    payment_data = {
        "Invoice": invoice_obj,
        "Account": account_obj,
        "Amount": amount,
        "Date": date,
    }

    if params.get("reference"):
        payment_data["Reference"] = params["reference"]

    result = _api_call(
        token, tenant_id, "Payments",
        method="POST",
        data={"Payments": [payment_data]}
    )

    if result.get("ok") and "result" in result:
        payments = result["result"].get("Payments", [])
        if payments:
            p = payments[0]
            return {
                "ok": True,
                "data": {
                    "payment_id": p.get("PaymentID"),
                    "date": p.get("Date"),
                    "amount": p.get("Amount"),
                    "reference": p.get("Reference"),
                    "status": p.get("Status"),
                    "invoice_number": p.get("Invoice", {}).get("InvoiceNumber"),
                }
            }
    return result


# =============================================================================
# Organisation Actions
# =============================================================================

def get_organisation(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get organisation details.

    Params:
        None required
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    tenant_id = _get_tenant_id(profile)

    result = _api_call(token, tenant_id, "Organisation")

    if result.get("ok") and "result" in result:
        orgs = result["result"].get("Organisations", [])
        if orgs:
            org = orgs[0]
            return {
                "ok": True,
                "data": {
                    "organisation_id": org.get("OrganisationID"),
                    "name": org.get("Name"),
                    "legal_name": org.get("LegalName"),
                    "short_code": org.get("ShortCode"),
                    "organisation_type": org.get("OrganisationType"),
                    "organisation_status": org.get("OrganisationStatus"),
                    "base_currency": org.get("BaseCurrency"),
                    "country_code": org.get("CountryCode"),
                    "timezone": org.get("Timezone"),
                    "line_of_business": org.get("LineOfBusiness"),
                    "registration_number": org.get("RegistrationNumber"),
                    "tax_number": org.get("TaxNumber"),
                    "financial_year_end_day": org.get("FinancialYearEndDay"),
                    "financial_year_end_month": org.get("FinancialYearEndMonth"),
                    "edition": org.get("Edition"),
                    "created_date_utc": org.get("CreatedDateUTC"),
                }
            }
        return {"ok": False, "error": "Organisation not found"}
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_invoices": list_invoices,
    "create_invoice": create_invoice,
    "get_invoice": get_invoice,
    "list_contacts": list_contacts,
    "create_contact": create_contact,
    "list_accounts": list_accounts,
    "create_payment": create_payment,
    "get_organisation": get_organisation,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """
    Main dispatch entry point.

    Called by ControllerDispatch with:
        - profile: The profile name from method_id
        - action: The action name from method_id
        - params: Action parameters

    Returns action result dict.
    """
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}

    logger.info(f"Executing xero.{profile}.{action}")
    return ACTIONS[action](profile, params)
