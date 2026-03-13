"""Example: Stripe controller — Customers, Payments, Subscriptions integration.

This is an example skeleton for a Stripe payment processing controller.
Requires Stripe secret key in environment variable.

Method IDs:
  controller.stripe.{profile}.list_customers
  controller.stripe.{profile}.create_customer
  controller.stripe.{profile}.list_payments
  controller.stripe.{profile}.create_payment_intent
  controller.stripe.{profile}.list_subscriptions
  controller.stripe.{profile}.create_invoice
  controller.stripe.{profile}.get_balance
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

log = logging.getLogger("tinyhive.controller.stripe")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

BASE_URL = "https://api.stripe.com/v1"


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'")
    return json.loads(path.read_text())


def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get Stripe secret API key from environment."""
    env_var = profile.get("api_key_env", "STRIPE_SECRET_KEY")
    api_key = os.environ.get(env_var, "")
    if not api_key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return api_key


def _api_call(
    api_key: str,
    endpoint: str,
    method: str = "GET",
    data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Make a Stripe API call using Basic Auth.

    Stripe API uses form-encoded data for POST requests and
    Basic Auth with the secret key as the username.
    """
    url = f"{BASE_URL}/{endpoint}"

    # Basic Auth: secret key as username, empty password
    credentials = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    body = None
    if data:
        # Flatten nested dicts for Stripe's form encoding (e.g., metadata[key]=value)
        flat_data = _flatten_dict(data)
        body = urlencode(flat_data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=30) as response:
            return {"ok": True, "data": json.loads(response.read().decode("utf-8"))}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("error", {}).get("message", error_body[:500])
        except json.JSONDecodeError:
            error_msg = error_body[:500]
        return {"ok": False, "error": f"HTTP {e.code}: {error_msg}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _flatten_dict(data: Dict[str, Any], parent_key: str = "") -> Dict[str, str]:
    """Flatten nested dict for Stripe form encoding.

    Example: {"metadata": {"order_id": "123"}} -> {"metadata[order_id]": "123"}
    """
    items = []
    for key, value in data.items():
        new_key = f"{parent_key}[{key}]" if parent_key else key
        if isinstance(value, dict):
            items.extend(_flatten_dict(value, new_key).items())
        elif isinstance(value, list):
            for i, v in enumerate(value):
                if isinstance(v, dict):
                    items.extend(_flatten_dict(v, f"{new_key}[{i}]").items())
                else:
                    items.append((f"{new_key}[{i}]", str(v)))
        elif value is not None:
            items.append((new_key, str(value)))
    return dict(items)


# ---------------------------------------------------------------------------
# Customer Actions
# ---------------------------------------------------------------------------

def list_customers(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List customers with pagination.

    Params:
        - limit: Number of customers to return (default: 10, max: 100)
        - starting_after: Cursor for pagination (customer ID)
        - email: Filter by email address
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    query_params = {}
    if params.get("limit"):
        query_params["limit"] = min(int(params["limit"]), 100)
    else:
        query_params["limit"] = 10

    if params.get("starting_after"):
        query_params["starting_after"] = params["starting_after"]

    if params.get("email"):
        query_params["email"] = params["email"]

    endpoint = "customers"
    if query_params:
        endpoint = f"customers?{urlencode(query_params)}"

    return _api_call(api_key, endpoint)


def create_customer(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new customer.

    Params:
        - email: Customer email address
        - name: Customer full name
        - description: Description of the customer
        - phone: Customer phone number
        - metadata: Dict of key-value pairs for custom data

    Note: Creating customers may require SPINE approval depending on policy.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    customer_data = {}

    if params.get("email"):
        customer_data["email"] = params["email"]
    if params.get("name"):
        customer_data["name"] = params["name"]
    if params.get("description"):
        customer_data["description"] = params["description"]
    if params.get("phone"):
        customer_data["phone"] = params["phone"]
    if params.get("metadata"):
        customer_data["metadata"] = params["metadata"]

    return _api_call(api_key, "customers", method="POST", data=customer_data)


# ---------------------------------------------------------------------------
# Payment Actions
# ---------------------------------------------------------------------------

def list_payments(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List payment intents with filters.

    Params:
        - limit: Number of payments to return (default: 10, max: 100)
        - starting_after: Cursor for pagination (payment intent ID)
        - customer: Filter by customer ID
        - created_gte: Filter by creation date >= (Unix timestamp)
        - created_lte: Filter by creation date <= (Unix timestamp)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    query_params = {}
    if params.get("limit"):
        query_params["limit"] = min(int(params["limit"]), 100)
    else:
        query_params["limit"] = 10

    if params.get("starting_after"):
        query_params["starting_after"] = params["starting_after"]

    if params.get("customer"):
        query_params["customer"] = params["customer"]

    if params.get("created_gte"):
        query_params["created[gte]"] = params["created_gte"]

    if params.get("created_lte"):
        query_params["created[lte]"] = params["created_lte"]

    endpoint = "payment_intents"
    if query_params:
        endpoint = f"payment_intents?{urlencode(query_params)}"

    return _api_call(api_key, endpoint)


def create_payment_intent(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a payment intent.

    Params:
        - amount: Amount in smallest currency unit (e.g., cents) (required)
        - currency: Three-letter ISO currency code (required, e.g., "usd")
        - customer: Customer ID to associate with payment
        - description: Description of the payment
        - metadata: Dict of key-value pairs for custom data
        - automatic_payment_methods: Enable automatic payment methods (default: True)

    Note: Creating payments requires SPINE approval.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    amount = params.get("amount")
    currency = params.get("currency")

    if not amount or not currency:
        return {"ok": False, "error": "amount and currency are required"}

    payment_data = {
        "amount": int(amount),
        "currency": currency.lower(),
    }

    if params.get("customer"):
        payment_data["customer"] = params["customer"]
    if params.get("description"):
        payment_data["description"] = params["description"]
    if params.get("metadata"):
        payment_data["metadata"] = params["metadata"]

    # Enable automatic payment methods by default
    if params.get("automatic_payment_methods", True):
        payment_data["automatic_payment_methods"] = {"enabled": "true"}

    return _api_call(api_key, "payment_intents", method="POST", data=payment_data)


# ---------------------------------------------------------------------------
# Subscription Actions
# ---------------------------------------------------------------------------

def list_subscriptions(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """List subscriptions with status filter.

    Params:
        - limit: Number of subscriptions to return (default: 10, max: 100)
        - starting_after: Cursor for pagination (subscription ID)
        - customer: Filter by customer ID
        - status: Filter by status (active, canceled, incomplete, past_due, trialing, all)
        - price: Filter by price ID
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    query_params = {}
    if params.get("limit"):
        query_params["limit"] = min(int(params["limit"]), 100)
    else:
        query_params["limit"] = 10

    if params.get("starting_after"):
        query_params["starting_after"] = params["starting_after"]

    if params.get("customer"):
        query_params["customer"] = params["customer"]

    if params.get("status"):
        query_params["status"] = params["status"]

    if params.get("price"):
        query_params["price"] = params["price"]

    endpoint = "subscriptions"
    if query_params:
        endpoint = f"subscriptions?{urlencode(query_params)}"

    return _api_call(api_key, endpoint)


# ---------------------------------------------------------------------------
# Invoice Actions
# ---------------------------------------------------------------------------

def create_invoice(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a draft invoice for a customer.

    Params:
        - customer: Customer ID (required)
        - description: Description for the invoice
        - metadata: Dict of key-value pairs for custom data
        - auto_advance: Auto-finalize the invoice (default: False for draft)
        - collection_method: "charge_automatically" or "send_invoice"
        - days_until_due: Days until invoice is due (for send_invoice method)

    Note: Creating invoices may require SPINE approval.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    customer = params.get("customer")
    if not customer:
        return {"ok": False, "error": "customer is required"}

    invoice_data = {
        "customer": customer,
        "auto_advance": "false",  # Create as draft by default
    }

    if params.get("description"):
        invoice_data["description"] = params["description"]
    if params.get("metadata"):
        invoice_data["metadata"] = params["metadata"]
    if params.get("auto_advance") is not None:
        invoice_data["auto_advance"] = "true" if params["auto_advance"] else "false"
    if params.get("collection_method"):
        invoice_data["collection_method"] = params["collection_method"]
    if params.get("days_until_due"):
        invoice_data["days_until_due"] = int(params["days_until_due"])

    return _api_call(api_key, "invoices", method="POST", data=invoice_data)


# ---------------------------------------------------------------------------
# Balance Actions
# ---------------------------------------------------------------------------

def get_balance(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get account balance.

    Params: None required.

    Returns the current account balance, broken down by currency and source types.
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)

    return _api_call(api_key, "balance")


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "list_customers": list_customers,
    "create_customer": create_customer,
    "list_payments": list_payments,
    "create_payment_intent": create_payment_intent,
    "list_subscriptions": list_subscriptions,
    "create_invoice": create_invoice,
    "get_balance": get_balance,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a profile."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'"}
    return ACTIONS[action](profile, params)
