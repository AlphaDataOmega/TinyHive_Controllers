"""QuickBooks Online Controller — Accounting integration via REST API.

This controller provides integration with QuickBooks Online API
for managing invoices, customers, payments, and accounting data.

Method IDs:
  controller.quickbooks.{profile}.create_invoice
  controller.quickbooks.{profile}.get_invoice
  controller.quickbooks.{profile}.list_invoices
  controller.quickbooks.{profile}.create_customer
  controller.quickbooks.{profile}.list_customers
  controller.quickbooks.{profile}.create_payment
  controller.quickbooks.{profile}.get_company_info
  controller.quickbooks.{profile}.query

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  {
    "realm_id": "123456789",
    "token_env": "QUICKBOOKS_ACCESS_TOKEN",
    "environment": "production"
  }

  Fields:
    - realm_id: Your QuickBooks company ID (required)
    - token_env: Environment variable containing OAuth2 access token
                 (default: QUICKBOOKS_ACCESS_TOKEN)
    - environment: "production" or "sandbox" (default: production)

Authentication:
  QuickBooks Online uses OAuth2. You need to:
  1. Create an app at https://developer.intuit.com
  2. Obtain OAuth2 access token via authorization flow
  3. Set the token in the environment variable specified by token_env

  Access tokens expire after 1 hour. Use refresh tokens to obtain new ones.

Dependencies:
  - None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.quickbooks")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# QuickBooks API endpoints
QB_PRODUCTION_BASE = "https://quickbooks.api.intuit.com/v3/company"
QB_SANDBOX_BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with QuickBooks configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available QuickBooks profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Authentication
# =============================================================================

def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get OAuth2 access token from environment."""
    env_var = profile.get("token_env", "QUICKBOOKS_ACCESS_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(
            f"Environment variable '{env_var}' not set. "
            "Obtain an OAuth2 access token from QuickBooks and set it."
        )
    return token


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get API base URL based on environment."""
    realm_id = profile.get("realm_id")
    if not realm_id:
        raise ValueError("realm_id is required in profile configuration")

    environment = profile.get("environment", "production")
    if environment == "sandbox":
        return f"{QB_SANDBOX_BASE}/{realm_id}"
    return f"{QB_PRODUCTION_BASE}/{realm_id}"


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated QuickBooks API call."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            # QuickBooks error format
            fault = error_data.get("Fault", {})
            errors = fault.get("Error", [])
            if errors:
                error_message = errors[0].get("Detail", errors[0].get("Message", error_body[:500]))
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("QuickBooks API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in QuickBooks API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Invoice Actions
# =============================================================================

def create_invoice(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new invoice in QuickBooks.

    Params:
        customer_ref (str|int): Customer ID reference (required)
        line_items (list): List of line items (required)
            Each item: {
                "description": str,
                "amount": float,
                "quantity": int (default: 1),
                "item_ref": str|int (optional, for inventory items)
            }
        due_date (str): Due date in YYYY-MM-DD format (optional)
        doc_number (str): Custom invoice number (optional)
        private_note (str): Internal memo (optional)
        customer_memo (str): Memo visible to customer (optional)

    Returns:
        Invoice object with Id, DocNumber, TotalAmt, etc.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    customer_ref = params.get("customer_ref")
    line_items = params.get("line_items", [])

    if not customer_ref:
        return {"ok": False, "error": "customer_ref is required"}
    if not line_items:
        return {"ok": False, "error": "line_items is required (at least one item)"}

    # Build invoice object
    invoice = {
        "CustomerRef": {"value": str(customer_ref)}
    }

    # Build line items
    lines = []
    for idx, item in enumerate(line_items, start=1):
        line = {
            "Id": str(idx),
            "LineNum": idx,
            "Amount": item.get("amount", 0),
            "DetailType": "SalesItemLineDetail",
            "SalesItemLineDetail": {
                "Qty": item.get("quantity", 1),
                "UnitPrice": item.get("amount", 0) / item.get("quantity", 1) if item.get("quantity", 1) else item.get("amount", 0)
            }
        }

        if item.get("description"):
            line["Description"] = item["description"]

        if item.get("item_ref"):
            line["SalesItemLineDetail"]["ItemRef"] = {"value": str(item["item_ref"])}

        lines.append(line)

    invoice["Line"] = lines

    if params.get("due_date"):
        invoice["DueDate"] = params["due_date"]

    if params.get("doc_number"):
        invoice["DocNumber"] = params["doc_number"]

    if params.get("private_note"):
        invoice["PrivateNote"] = params["private_note"]

    if params.get("customer_memo"):
        invoice["CustomerMemo"] = {"value": params["customer_memo"]}

    url = f"{base_url}/invoice"
    result = _api_call(token, url, method="POST", data=json.dumps(invoice).encode("utf-8"))

    if result.get("ok") and "result" in result:
        inv = result["result"].get("Invoice", {})
        return {
            "ok": True,
            "data": {
                "id": inv.get("Id"),
                "doc_number": inv.get("DocNumber"),
                "total_amount": inv.get("TotalAmt"),
                "balance": inv.get("Balance"),
                "due_date": inv.get("DueDate"),
                "customer_ref": inv.get("CustomerRef", {}).get("value"),
                "status": inv.get("PrintStatus"),
                "create_time": inv.get("MetaData", {}).get("CreateTime"),
            }
        }
    return result


def get_invoice(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get an invoice by ID.

    Params:
        invoice_id (str|int): Invoice ID (required)

    Returns:
        Full invoice object.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    invoice_id = params.get("invoice_id")
    if not invoice_id:
        return {"ok": False, "error": "invoice_id is required"}

    url = f"{base_url}/invoice/{invoice_id}"
    result = _api_call(token, url, method="GET")

    if result.get("ok") and "result" in result:
        inv = result["result"].get("Invoice", {})
        return {
            "ok": True,
            "data": {
                "id": inv.get("Id"),
                "doc_number": inv.get("DocNumber"),
                "total_amount": inv.get("TotalAmt"),
                "balance": inv.get("Balance"),
                "due_date": inv.get("DueDate"),
                "customer_ref": inv.get("CustomerRef", {}).get("value"),
                "customer_name": inv.get("CustomerRef", {}).get("name"),
                "line_items": [
                    {
                        "id": line.get("Id"),
                        "description": line.get("Description"),
                        "amount": line.get("Amount"),
                        "detail_type": line.get("DetailType"),
                    }
                    for line in inv.get("Line", [])
                ],
                "email_status": inv.get("EmailStatus"),
                "print_status": inv.get("PrintStatus"),
                "create_time": inv.get("MetaData", {}).get("CreateTime"),
                "last_updated": inv.get("MetaData", {}).get("LastUpdatedTime"),
            }
        }
    return result


def list_invoices(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List invoices with optional filters.

    Params:
        max_results (int): Maximum results to return (default: 100, max: 1000)
        start_position (int): Starting position for pagination (default: 1)
        customer_id (str|int): Filter by customer ID (optional)
        due_date_from (str): Filter by due date >= YYYY-MM-DD (optional)
        due_date_to (str): Filter by due date <= YYYY-MM-DD (optional)

    Returns:
        List of invoice summaries.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    max_results = min(params.get("max_results", 100), 1000)
    start_position = params.get("start_position", 1)

    # Build query
    conditions = []

    if params.get("customer_id"):
        conditions.append(f"CustomerRef = '{params['customer_id']}'")

    if params.get("due_date_from"):
        conditions.append(f"DueDate >= '{params['due_date_from']}'")

    if params.get("due_date_to"):
        conditions.append(f"DueDate <= '{params['due_date_to']}'")

    where_clause = " AND ".join(conditions) if conditions else ""

    query = f"SELECT * FROM Invoice"
    if where_clause:
        query += f" WHERE {where_clause}"
    query += f" MAXRESULTS {max_results} STARTPOSITION {start_position}"

    url = f"{base_url}/query?query={quote(query)}"
    result = _api_call(token, url, method="GET")

    if result.get("ok") and "result" in result:
        query_response = result["result"].get("QueryResponse", {})
        invoices = query_response.get("Invoice", [])
        return {
            "ok": True,
            "data": {
                "invoices": [
                    {
                        "id": inv.get("Id"),
                        "doc_number": inv.get("DocNumber"),
                        "total_amount": inv.get("TotalAmt"),
                        "balance": inv.get("Balance"),
                        "due_date": inv.get("DueDate"),
                        "customer_ref": inv.get("CustomerRef", {}).get("value"),
                        "customer_name": inv.get("CustomerRef", {}).get("name"),
                    }
                    for inv in invoices
                ],
                "count": len(invoices),
                "start_position": start_position,
                "max_results": max_results,
            }
        }
    return result


# =============================================================================
# Customer Actions
# =============================================================================

def create_customer(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new customer in QuickBooks.

    Params:
        display_name (str): Customer display name (required, must be unique)
        email (str): Primary email address (optional)
        phone (str): Primary phone number (optional)
        company_name (str): Company name (optional)
        given_name (str): First name (optional)
        family_name (str): Last name (optional)
        billing_address (dict): Billing address (optional)
            {
                "line1": str,
                "city": str,
                "country_sub_division_code": str (state/province),
                "postal_code": str,
                "country": str
            }
        notes (str): Customer notes (optional)

    Returns:
        Customer object with Id, DisplayName, etc.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    display_name = params.get("display_name")
    if not display_name:
        return {"ok": False, "error": "display_name is required"}

    customer = {
        "DisplayName": display_name
    }

    if params.get("email"):
        customer["PrimaryEmailAddr"] = {"Address": params["email"]}

    if params.get("phone"):
        customer["PrimaryPhone"] = {"FreeFormNumber": params["phone"]}

    if params.get("company_name"):
        customer["CompanyName"] = params["company_name"]

    if params.get("given_name"):
        customer["GivenName"] = params["given_name"]

    if params.get("family_name"):
        customer["FamilyName"] = params["family_name"]

    if params.get("notes"):
        customer["Notes"] = params["notes"]

    billing_addr = params.get("billing_address")
    if billing_addr:
        customer["BillAddr"] = {
            "Line1": billing_addr.get("line1", ""),
            "City": billing_addr.get("city", ""),
            "CountrySubDivisionCode": billing_addr.get("country_sub_division_code", ""),
            "PostalCode": billing_addr.get("postal_code", ""),
            "Country": billing_addr.get("country", ""),
        }

    url = f"{base_url}/customer"
    result = _api_call(token, url, method="POST", data=json.dumps(customer).encode("utf-8"))

    if result.get("ok") and "result" in result:
        cust = result["result"].get("Customer", {})
        return {
            "ok": True,
            "data": {
                "id": cust.get("Id"),
                "display_name": cust.get("DisplayName"),
                "company_name": cust.get("CompanyName"),
                "email": cust.get("PrimaryEmailAddr", {}).get("Address"),
                "phone": cust.get("PrimaryPhone", {}).get("FreeFormNumber"),
                "balance": cust.get("Balance"),
                "active": cust.get("Active"),
                "create_time": cust.get("MetaData", {}).get("CreateTime"),
            }
        }
    return result


def list_customers(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List customers with optional filters.

    Params:
        max_results (int): Maximum results to return (default: 100, max: 1000)
        start_position (int): Starting position for pagination (default: 1)
        active (bool): Filter by active status (optional)
        display_name (str): Filter by display name (partial match) (optional)

    Returns:
        List of customer summaries.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    max_results = min(params.get("max_results", 100), 1000)
    start_position = params.get("start_position", 1)

    # Build query
    conditions = []

    if params.get("active") is not None:
        active_val = "true" if params["active"] else "false"
        conditions.append(f"Active = {active_val}")

    if params.get("display_name"):
        conditions.append(f"DisplayName LIKE '%{params['display_name']}%'")

    where_clause = " AND ".join(conditions) if conditions else ""

    query = f"SELECT * FROM Customer"
    if where_clause:
        query += f" WHERE {where_clause}"
    query += f" MAXRESULTS {max_results} STARTPOSITION {start_position}"

    url = f"{base_url}/query?query={quote(query)}"
    result = _api_call(token, url, method="GET")

    if result.get("ok") and "result" in result:
        query_response = result["result"].get("QueryResponse", {})
        customers = query_response.get("Customer", [])
        return {
            "ok": True,
            "data": {
                "customers": [
                    {
                        "id": cust.get("Id"),
                        "display_name": cust.get("DisplayName"),
                        "company_name": cust.get("CompanyName"),
                        "email": cust.get("PrimaryEmailAddr", {}).get("Address"),
                        "phone": cust.get("PrimaryPhone", {}).get("FreeFormNumber"),
                        "balance": cust.get("Balance"),
                        "active": cust.get("Active"),
                    }
                    for cust in customers
                ],
                "count": len(customers),
                "start_position": start_position,
                "max_results": max_results,
            }
        }
    return result


# =============================================================================
# Payment Actions
# =============================================================================

def create_payment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Record a payment received from a customer.

    Params:
        customer_ref (str|int): Customer ID reference (required)
        amount (float): Payment amount (required)
        payment_method (str): Payment method - Cash, Check, CreditCard, etc. (optional)
        payment_ref_num (str): Reference number (check number, etc.) (optional)
        deposit_to_account (str|int): Account ID to deposit to (optional)
        invoice_refs (list): List of invoice IDs to apply payment to (optional)
            Each: {"invoice_id": str, "amount": float}
        txn_date (str): Transaction date YYYY-MM-DD (optional, default: today)
        private_note (str): Internal memo (optional)

    Returns:
        Payment object with Id, TotalAmt, etc.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    customer_ref = params.get("customer_ref")
    amount = params.get("amount")

    if not customer_ref:
        return {"ok": False, "error": "customer_ref is required"}
    if amount is None:
        return {"ok": False, "error": "amount is required"}

    payment = {
        "CustomerRef": {"value": str(customer_ref)},
        "TotalAmt": amount
    }

    if params.get("payment_method"):
        payment["PaymentMethodRef"] = {"value": params["payment_method"]}

    if params.get("payment_ref_num"):
        payment["PaymentRefNum"] = params["payment_ref_num"]

    if params.get("deposit_to_account"):
        payment["DepositToAccountRef"] = {"value": str(params["deposit_to_account"])}

    if params.get("txn_date"):
        payment["TxnDate"] = params["txn_date"]

    if params.get("private_note"):
        payment["PrivateNote"] = params["private_note"]

    # Link to invoices if specified
    invoice_refs = params.get("invoice_refs", [])
    if invoice_refs:
        lines = []
        for inv_ref in invoice_refs:
            line = {
                "Amount": inv_ref.get("amount", amount),
                "LinkedTxn": [{
                    "TxnId": str(inv_ref.get("invoice_id")),
                    "TxnType": "Invoice"
                }]
            }
            lines.append(line)
        payment["Line"] = lines

    url = f"{base_url}/payment"
    result = _api_call(token, url, method="POST", data=json.dumps(payment).encode("utf-8"))

    if result.get("ok") and "result" in result:
        pmt = result["result"].get("Payment", {})
        return {
            "ok": True,
            "data": {
                "id": pmt.get("Id"),
                "total_amount": pmt.get("TotalAmt"),
                "customer_ref": pmt.get("CustomerRef", {}).get("value"),
                "txn_date": pmt.get("TxnDate"),
                "payment_ref_num": pmt.get("PaymentRefNum"),
                "unapplied_amount": pmt.get("UnappliedAmt"),
                "create_time": pmt.get("MetaData", {}).get("CreateTime"),
            }
        }
    return result


# =============================================================================
# Company Info Actions
# =============================================================================

def get_company_info(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get company information for the connected QuickBooks account.

    Params:
        None required.

    Returns:
        Company info including name, address, fiscal year, etc.
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)
    realm_id = profile.get("realm_id")

    url = f"{base_url}/companyinfo/{realm_id}"
    result = _api_call(token, url, method="GET")

    if result.get("ok") and "result" in result:
        info = result["result"].get("CompanyInfo", {})
        return {
            "ok": True,
            "data": {
                "id": info.get("Id"),
                "company_name": info.get("CompanyName"),
                "legal_name": info.get("LegalName"),
                "email": info.get("Email", {}).get("Address"),
                "phone": info.get("PrimaryPhone", {}).get("FreeFormNumber"),
                "address": {
                    "line1": info.get("CompanyAddr", {}).get("Line1"),
                    "city": info.get("CompanyAddr", {}).get("City"),
                    "state": info.get("CompanyAddr", {}).get("CountrySubDivisionCode"),
                    "postal_code": info.get("CompanyAddr", {}).get("PostalCode"),
                    "country": info.get("CompanyAddr", {}).get("Country"),
                },
                "fiscal_year_start": info.get("FiscalYearStartMonth"),
                "country": info.get("Country"),
                "supported_languages": info.get("SupportedLanguages"),
                "create_time": info.get("MetaData", {}).get("CreateTime"),
            }
        }
    return result


# =============================================================================
# Query Action
# =============================================================================

def query(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a SQL-like query against QuickBooks data.

    QuickBooks supports a limited SQL-like query language for retrieving data.

    Params:
        query (str): SQL-like query string (required)
            Examples:
              "SELECT * FROM Customer"
              "SELECT * FROM Invoice WHERE TotalAmt > '100'"
              "SELECT * FROM Item WHERE Type = 'Service'"
              "SELECT COUNT(*) FROM Customer"

    Returns:
        Query results.

    Supported entities:
        Account, Bill, BillPayment, Class, CompanyInfo, CreditMemo,
        Customer, Department, Deposit, Employee, Estimate, Invoice,
        Item, JournalEntry, Payment, PaymentMethod, Purchase, PurchaseOrder,
        RefundReceipt, SalesReceipt, TaxCode, TaxRate, Term, TimeActivity,
        Transfer, Vendor, VendorCredit
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    query_string = params.get("query")
    if not query_string:
        return {"ok": False, "error": "query string is required"}

    url = f"{base_url}/query?query={quote(query_string)}"
    result = _api_call(token, url, method="GET")

    if result.get("ok") and "result" in result:
        query_response = result["result"].get("QueryResponse", {})

        # Find the entity type in the response
        entity_data = None
        entity_type = None
        for key in query_response:
            if key not in ("startPosition", "maxResults", "totalCount"):
                entity_type = key
                entity_data = query_response[key]
                break

        return {
            "ok": True,
            "data": {
                "entity_type": entity_type,
                "results": entity_data if entity_data else [],
                "count": len(entity_data) if entity_data else 0,
                "total_count": query_response.get("totalCount"),
                "start_position": query_response.get("startPosition"),
                "max_results": query_response.get("maxResults"),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "create_invoice": create_invoice,
    "get_invoice": get_invoice,
    "list_invoices": list_invoices,
    "create_customer": create_customer,
    "list_customers": list_customers,
    "create_payment": create_payment,
    "get_company_info": get_company_info,
    "query": query,
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
        return {"ok": False, "error": f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"}

    try:
        logger.info(f"Executing quickbooks.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
