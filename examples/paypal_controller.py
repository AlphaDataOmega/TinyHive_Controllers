"""PayPal Controller for TinyHive

A PayPal REST API controller supporting payment processing, payouts, invoicing,
and transaction management using OAuth 2.0 client credentials authentication.

Method IDs:
  controller.paypal.{profile}.create_order
  controller.paypal.{profile}.capture_order
  controller.paypal.{profile}.get_order
  controller.paypal.{profile}.create_payout
  controller.paypal.{profile}.list_transactions
  controller.paypal.{profile}.create_invoice
  controller.paypal.{profile}.send_invoice
  controller.paypal.{profile}.refund_capture

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Example profile:
{
    "environment": "sandbox",
    "client_id_env": "PAYPAL_CLIENT_ID",
    "client_secret_env": "PAYPAL_CLIENT_SECRET",
    "default_currency": "USD"
}

Environment Variables:
- PAYPAL_CLIENT_ID: Your PayPal REST API client ID
- PAYPAL_CLIENT_SECRET: Your PayPal REST API client secret

API Endpoints:
- Sandbox: https://api-m.sandbox.paypal.com
- Production: https://api-m.paypal.com

Dependencies:
- None (standard library only)
"""

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.paypal")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# PayPal API base URLs
PAYPAL_SANDBOX_URL = "https://api-m.sandbox.paypal.com"
PAYPAL_PRODUCTION_URL = "https://api-m.paypal.com"

# Token cache: profile_name -> (token, expiry_timestamp)
_token_cache: Dict[str, Tuple[str, float]] = {}

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile from the profiles directory."""
    profile_path = PROFILES_DIR / f"{name}.json"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {name}. Create {profile_path} with PayPal configuration.")

    with open(profile_path) as f:
        return json.load(f)


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the PayPal API base URL based on environment."""
    environment = profile.get("environment", "sandbox").lower()
    if environment == "production" or environment == "live":
        return PAYPAL_PRODUCTION_URL
    return PAYPAL_SANDBOX_URL


# =============================================================================
# OAuth 2.0 Authentication
# =============================================================================

def _get_access_token(profile: Dict[str, Any], profile_name: str) -> str:
    """
    Get OAuth 2.0 access token using client credentials grant.

    PayPal uses HTTP Basic Auth with client_id:client_secret to obtain tokens.
    """
    # Check cache first
    if profile_name in _token_cache:
        token, expiry = _token_cache[profile_name]
        if time.time() < expiry:
            return token

    # Get credentials from environment
    client_id_env = profile.get("client_id_env", "PAYPAL_CLIENT_ID")
    client_secret_env = profile.get("client_secret_env", "PAYPAL_CLIENT_SECRET")

    client_id = os.environ.get(client_id_env)
    client_secret = os.environ.get(client_secret_env)

    if not client_id:
        raise ValueError(f"Missing environment variable: {client_id_env}")
    if not client_secret:
        raise ValueError(f"Missing environment variable: {client_secret_env}")

    # Prepare Basic Auth header
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("ascii")

    base_url = _get_base_url(profile)
    token_url = f"{base_url}/v1/oauth2/token"

    # Request body
    data = urlencode({"grant_type": "client_credentials"}).encode("utf-8")

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    try:
        req = Request(token_url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=30) as response:
            token_data = json.loads(response.read().decode("utf-8"))

        access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        # Cache with 60 second buffer before expiry
        expiry = time.time() + expires_in - 60

        _token_cache[profile_name] = (access_token, expiry)
        logger.info(f"Obtained new PayPal access token for profile '{profile_name}'")
        return access_token

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"Failed to obtain access token: HTTP {e.code}: {error_body}")
    except URLError as e:
        raise ValueError(f"Failed to obtain access token: {e.reason}")


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    base_url: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Make an authenticated PayPal API call."""
    url = f"{base_url}{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            # PayPal error format
            if "message" in error_data:
                error_message = error_data["message"]
            elif "error_description" in error_data:
                error_message = error_data["error_description"]
            elif "details" in error_data and error_data["details"]:
                error_message = "; ".join(d.get("description", d.get("issue", "")) for d in error_data["details"])
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("PayPal API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in PayPal API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Order Actions
# =============================================================================

def create_order(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a PayPal payment order.

    Params:
        intent (str): Payment intent - 'CAPTURE' or 'AUTHORIZE' (default: CAPTURE)
        purchase_units (list): List of purchase unit objects, each containing:
            - amount (dict): Required. Contains 'currency_code' and 'value'
            - description (str): Optional description
            - reference_id (str): Optional reference ID
            - custom_id (str): Optional custom ID for tracking
        return_url (str): URL to redirect after approval (optional)
        cancel_url (str): URL to redirect on cancel (optional)

    Example params:
        {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {"currency_code": "USD", "value": "100.00"},
                    "description": "Product purchase"
                }
            ]
        }
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    intent = params.get("intent", "CAPTURE").upper()
    if intent not in ("CAPTURE", "AUTHORIZE"):
        return {"ok": False, "error": "intent must be 'CAPTURE' or 'AUTHORIZE'"}

    purchase_units = params.get("purchase_units")
    if not purchase_units:
        return {"ok": False, "error": "purchase_units is required"}

    # Build purchase units with default currency from profile if not specified
    default_currency = profile.get("default_currency", "USD")
    formatted_units = []
    for i, unit in enumerate(purchase_units):
        if "amount" not in unit:
            return {"ok": False, "error": f"purchase_units[{i}] missing 'amount'"}

        amount = unit["amount"]
        if isinstance(amount, (int, float, str)):
            # Simple amount value, use default currency
            amount = {"currency_code": default_currency, "value": str(amount)}
        elif isinstance(amount, dict):
            if "value" not in amount:
                return {"ok": False, "error": f"purchase_units[{i}].amount missing 'value'"}
            if "currency_code" not in amount:
                amount["currency_code"] = default_currency
            amount["value"] = str(amount["value"])

        formatted_unit = {"amount": amount}

        if "description" in unit:
            formatted_unit["description"] = unit["description"]
        if "reference_id" in unit:
            formatted_unit["reference_id"] = unit["reference_id"]
        if "custom_id" in unit:
            formatted_unit["custom_id"] = unit["custom_id"]

        formatted_units.append(formatted_unit)

    order_data: Dict[str, Any] = {
        "intent": intent,
        "purchase_units": formatted_units,
    }

    # Add application context if return/cancel URLs provided
    return_url = params.get("return_url")
    cancel_url = params.get("cancel_url")
    if return_url or cancel_url:
        order_data["application_context"] = {}
        if return_url:
            order_data["application_context"]["return_url"] = return_url
        if cancel_url:
            order_data["application_context"]["cancel_url"] = cancel_url

    result = _api_call(token, base_url, "/v2/checkout/orders", method="POST", data=order_data)

    if result.get("ok") and "data" in result:
        order = result["data"]
        # Extract approval link
        approval_url = None
        for link in order.get("links", []):
            if link.get("rel") == "approve":
                approval_url = link.get("href")
                break

        return {
            "ok": True,
            "result": {
                "order_id": order.get("id"),
                "status": order.get("status"),
                "approval_url": approval_url,
                "links": order.get("links", []),
            }
        }
    return result


def capture_order(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Capture an authorized PayPal order.

    Params:
        order_id (str): The PayPal order ID to capture (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    order_id = params.get("order_id")
    if not order_id:
        return {"ok": False, "error": "order_id is required"}

    result = _api_call(
        token, base_url, f"/v2/checkout/orders/{order_id}/capture",
        method="POST", data={}
    )

    if result.get("ok") and "data" in result:
        capture = result["data"]
        # Extract capture details
        captures = []
        for pu in capture.get("purchase_units", []):
            for cap in pu.get("payments", {}).get("captures", []):
                captures.append({
                    "capture_id": cap.get("id"),
                    "status": cap.get("status"),
                    "amount": cap.get("amount"),
                    "final_capture": cap.get("final_capture"),
                })

        return {
            "ok": True,
            "result": {
                "order_id": capture.get("id"),
                "status": capture.get("status"),
                "payer": capture.get("payer"),
                "captures": captures,
            }
        }
    return result


def get_order(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a PayPal order.

    Params:
        order_id (str): The PayPal order ID to retrieve (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    order_id = params.get("order_id")
    if not order_id:
        return {"ok": False, "error": "order_id is required"}

    result = _api_call(token, base_url, f"/v2/checkout/orders/{order_id}", method="GET")

    if result.get("ok") and "data" in result:
        order = result["data"]
        return {
            "ok": True,
            "result": {
                "order_id": order.get("id"),
                "status": order.get("status"),
                "intent": order.get("intent"),
                "purchase_units": order.get("purchase_units", []),
                "payer": order.get("payer"),
                "create_time": order.get("create_time"),
                "update_time": order.get("update_time"),
                "links": order.get("links", []),
            }
        }
    return result


# =============================================================================
# Payout Actions
# =============================================================================

def create_payout(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a PayPal payout (send money).

    Params:
        recipient_type (str): Type of recipient - 'EMAIL', 'PHONE', or 'PAYPAL_ID' (default: EMAIL)
        receiver (str): Recipient email, phone, or PayPal ID (required)
        amount (str/float): Amount to send (required)
        currency (str): Currency code (default: from profile or USD)
        note (str): Note to recipient (optional)
        sender_batch_id (str): Unique batch ID (optional, auto-generated if not provided)
        email_subject (str): Subject for payout email (optional)
        email_message (str): Message for payout email (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    recipient_type = params.get("recipient_type", "EMAIL").upper()
    if recipient_type not in ("EMAIL", "PHONE", "PAYPAL_ID"):
        return {"ok": False, "error": "recipient_type must be 'EMAIL', 'PHONE', or 'PAYPAL_ID'"}

    receiver = params.get("receiver")
    if not receiver:
        return {"ok": False, "error": "receiver is required"}

    amount = params.get("amount")
    if amount is None:
        return {"ok": False, "error": "amount is required"}

    currency = params.get("currency", profile.get("default_currency", "USD"))
    note = params.get("note", "")

    # Generate batch ID if not provided
    sender_batch_id = params.get("sender_batch_id", f"batch_{int(time.time() * 1000)}")

    payout_data = {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "recipient_type": recipient_type,
        },
        "items": [
            {
                "recipient_type": recipient_type,
                "receiver": receiver,
                "amount": {
                    "currency": currency,
                    "value": str(amount),
                },
                "note": note,
                "sender_item_id": f"item_{int(time.time() * 1000)}",
            }
        ]
    }

    # Add optional email fields
    if params.get("email_subject"):
        payout_data["sender_batch_header"]["email_subject"] = params["email_subject"]
    if params.get("email_message"):
        payout_data["sender_batch_header"]["email_message"] = params["email_message"]

    result = _api_call(token, base_url, "/v1/payments/payouts", method="POST", data=payout_data)

    if result.get("ok") and "data" in result:
        batch = result["data"].get("batch_header", {})
        return {
            "ok": True,
            "result": {
                "payout_batch_id": batch.get("payout_batch_id"),
                "batch_status": batch.get("batch_status"),
                "sender_batch_id": batch.get("sender_batch_header", {}).get("sender_batch_id"),
                "links": result["data"].get("links", []),
            }
        }
    return result


# =============================================================================
# Transaction Actions
# =============================================================================

def list_transactions(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List transactions for the PayPal account.

    Params:
        start_date (str): Start date in ISO 8601 format (required, e.g., '2024-01-01T00:00:00Z')
        end_date (str): End date in ISO 8601 format (required)
        transaction_type (str): Filter by transaction type (optional)
            Values: 'T0000' (all), 'T0001' (payment), 'T0002' (auth), etc.
        transaction_status (str): Filter by status (optional)
            Values: 'D' (denied), 'P' (pending), 'S' (success), 'V' (reversed)
        page_size (int): Number of records per page (default: 100, max: 500)
        page (int): Page number to retrieve (default: 1)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    start_date = params.get("start_date")
    end_date = params.get("end_date")

    if not start_date:
        return {"ok": False, "error": "start_date is required (ISO 8601 format)"}
    if not end_date:
        return {"ok": False, "error": "end_date is required (ISO 8601 format)"}

    # Build query parameters
    query_params = {
        "start_date": start_date,
        "end_date": end_date,
        "fields": "all",
        "page_size": str(params.get("page_size", 100)),
        "page": str(params.get("page", 1)),
    }

    if params.get("transaction_type"):
        query_params["transaction_type"] = params["transaction_type"]
    if params.get("transaction_status"):
        query_params["transaction_status"] = params["transaction_status"]

    query_string = urlencode(query_params)
    endpoint = f"/v1/reporting/transactions?{query_string}"

    result = _api_call(token, base_url, endpoint, method="GET")

    if result.get("ok") and "data" in result:
        data = result["data"]
        transactions = []
        for txn in data.get("transaction_details", []):
            txn_info = txn.get("transaction_info", {})
            payer_info = txn.get("payer_info", {})
            transactions.append({
                "transaction_id": txn_info.get("transaction_id"),
                "transaction_type": txn_info.get("transaction_event_code"),
                "transaction_status": txn_info.get("transaction_status"),
                "transaction_amount": txn_info.get("transaction_amount"),
                "fee_amount": txn_info.get("fee_amount"),
                "transaction_date": txn_info.get("transaction_initiation_date"),
                "payer_email": payer_info.get("email_address"),
                "payer_name": payer_info.get("payer_name"),
            })

        return {
            "ok": True,
            "result": {
                "transactions": transactions,
                "total_items": data.get("total_items", len(transactions)),
                "total_pages": data.get("total_pages", 1),
                "page": data.get("page", 1),
            }
        }
    return result


# =============================================================================
# Invoice Actions
# =============================================================================

def create_invoice(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a PayPal invoice.

    Params:
        invoice_number (str): Unique invoice number (optional, auto-generated if not provided)
        items (list): List of invoice items (required), each containing:
            - name (str): Item name (required)
            - quantity (str/int): Quantity (required)
            - unit_amount (dict or float): Amount per unit (required)
                If dict: {"currency_code": "USD", "value": "10.00"}
                If float/str: uses default currency
            - description (str): Item description (optional)
        recipient_email (str): Recipient email address (required)
        note (str): Note to recipient (optional)
        terms (str): Terms and conditions (optional)
        due_date (str): Due date in YYYY-MM-DD format (optional)
        currency (str): Currency code (default: from profile or USD)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    items = params.get("items")
    if not items:
        return {"ok": False, "error": "items is required"}

    recipient_email = params.get("recipient_email")
    if not recipient_email:
        return {"ok": False, "error": "recipient_email is required"}

    default_currency = params.get("currency", profile.get("default_currency", "USD"))

    # Format items
    formatted_items = []
    for i, item in enumerate(items):
        if "name" not in item:
            return {"ok": False, "error": f"items[{i}] missing 'name'"}
        if "quantity" not in item:
            return {"ok": False, "error": f"items[{i}] missing 'quantity'"}
        if "unit_amount" not in item:
            return {"ok": False, "error": f"items[{i}] missing 'unit_amount'"}

        unit_amount = item["unit_amount"]
        if isinstance(unit_amount, (int, float, str)):
            unit_amount = {"currency_code": default_currency, "value": str(unit_amount)}
        elif isinstance(unit_amount, dict):
            if "value" not in unit_amount:
                return {"ok": False, "error": f"items[{i}].unit_amount missing 'value'"}
            if "currency_code" not in unit_amount:
                unit_amount["currency_code"] = default_currency
            unit_amount["value"] = str(unit_amount["value"])

        formatted_item = {
            "name": item["name"],
            "quantity": str(item["quantity"]),
            "unit_amount": unit_amount,
        }

        if "description" in item:
            formatted_item["description"] = item["description"]

        formatted_items.append(formatted_item)

    invoice_data: Dict[str, Any] = {
        "detail": {
            "currency_code": default_currency,
        },
        "primary_recipients": [
            {
                "billing_info": {
                    "email_address": recipient_email,
                }
            }
        ],
        "items": formatted_items,
    }

    # Add optional fields
    if params.get("invoice_number"):
        invoice_data["detail"]["invoice_number"] = params["invoice_number"]
    if params.get("note"):
        invoice_data["detail"]["note"] = params["note"]
    if params.get("terms"):
        invoice_data["detail"]["terms_and_conditions"] = params["terms"]
    if params.get("due_date"):
        invoice_data["detail"]["payment_term"] = {
            "due_date": params["due_date"]
        }

    result = _api_call(token, base_url, "/v2/invoicing/invoices", method="POST", data=invoice_data)

    if result.get("ok") and "data" in result:
        invoice = result["data"]
        # Extract invoice ID from href
        invoice_id = None
        href = invoice.get("href", "")
        if "/invoices/" in href:
            invoice_id = href.split("/invoices/")[-1]

        return {
            "ok": True,
            "result": {
                "invoice_id": invoice_id,
                "href": href,
                "links": invoice.get("links", []) if isinstance(invoice, dict) else [],
            }
        }
    return result


def send_invoice(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a PayPal invoice to the recipient.

    Params:
        invoice_id (str): The PayPal invoice ID to send (required)
        subject (str): Email subject (optional)
        note (str): Note to include in email (optional)
        send_to_recipient (bool): Send to recipient (default: true)
        send_to_invoicer (bool): Send copy to invoicer (default: false)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    invoice_id = params.get("invoice_id")
    if not invoice_id:
        return {"ok": False, "error": "invoice_id is required"}

    send_data: Dict[str, Any] = {
        "send_to_recipient": params.get("send_to_recipient", True),
        "send_to_invoicer": params.get("send_to_invoicer", False),
    }

    if params.get("subject"):
        send_data["subject"] = params["subject"]
    if params.get("note"):
        send_data["note"] = params["note"]

    result = _api_call(
        token, base_url, f"/v2/invoicing/invoices/{invoice_id}/send",
        method="POST", data=send_data
    )

    if result.get("ok"):
        return {
            "ok": True,
            "result": {
                "invoice_id": invoice_id,
                "status": "sent",
            }
        }
    return result


# =============================================================================
# Refund Actions
# =============================================================================

def refund_capture(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Refund a captured payment.

    Params:
        capture_id (str): The capture ID to refund (required)
        amount (str/float): Amount to refund (optional, full refund if not specified)
        currency (str): Currency code (required if amount specified)
        note (str): Note to payer about the refund (optional)
        invoice_id (str): Your own invoice ID for tracking (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)
    base_url = _get_base_url(profile)

    capture_id = params.get("capture_id")
    if not capture_id:
        return {"ok": False, "error": "capture_id is required"}

    refund_data: Dict[str, Any] = {}

    # If amount specified, it's a partial refund
    if params.get("amount") is not None:
        currency = params.get("currency", profile.get("default_currency", "USD"))
        refund_data["amount"] = {
            "currency_code": currency,
            "value": str(params["amount"]),
        }

    if params.get("note"):
        refund_data["note_to_payer"] = params["note"]

    if params.get("invoice_id"):
        refund_data["invoice_id"] = params["invoice_id"]

    # Use empty dict for full refund
    result = _api_call(
        token, base_url, f"/v2/payments/captures/{capture_id}/refund",
        method="POST", data=refund_data if refund_data else {}
    )

    if result.get("ok") and "data" in result:
        refund = result["data"]
        return {
            "ok": True,
            "result": {
                "refund_id": refund.get("id"),
                "status": refund.get("status"),
                "amount": refund.get("amount"),
                "note_to_payer": refund.get("note_to_payer"),
                "create_time": refund.get("create_time"),
                "links": refund.get("links", []),
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "create_order": create_order,
    "capture_order": capture_order,
    "get_order": get_order,
    "create_payout": create_payout,
    "list_transactions": list_transactions,
    "create_invoice": create_invoice,
    "send_invoice": send_invoice,
    "refund_capture": refund_capture,
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
        logger.info(f"Executing paypal.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
