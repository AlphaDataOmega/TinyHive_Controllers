"""
Shopify Controller for TinyHive

A controller for interacting with the Shopify Admin REST API.

Method IDs:
  controller.shopify.{profile}.list_orders
  controller.shopify.{profile}.get_order
  controller.shopify.{profile}.create_order
  controller.shopify.{profile}.update_order
  controller.shopify.{profile}.list_products
  controller.shopify.{profile}.get_product
  controller.shopify.{profile}.update_inventory
  controller.shopify.{profile}.list_customers
  controller.shopify.{profile}.create_fulfillment

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Example profile:
{
    "store": "mystore.myshopify.com",
    "token_env": "SHOPIFY_ACCESS_TOKEN",
    "api_version": "2024-01"
}

Required Scopes:
---------------
- list_orders, get_order: read_orders
- create_order, update_order: write_orders
- list_products, get_product: read_products
- update_inventory: write_inventory
- list_customers: read_customers
- create_fulfillment: write_fulfillments

Dependencies:
------------
None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.shopify")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

DEFAULT_API_VERSION = "2024-01"
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


def list_profiles() -> List[str]:
    """List available Shopify profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# HTTP Helpers
# =============================================================================

def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get the Shopify access token from environment."""
    env_var = profile.get("token_env", "SHOPIFY_ACCESS_TOKEN")
    token = os.environ.get(env_var)
    if not token:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return token


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the base URL for Shopify Admin API."""
    store = profile.get("store", "")
    if not store:
        raise ValueError("Profile must specify 'store' (e.g., mystore.myshopify.com)")
    api_version = profile.get("api_version", DEFAULT_API_VERSION)
    return f"https://{store}/admin/api/{api_version}"


def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated Shopify API call."""
    token = _get_access_token(profile)
    base_url = _get_base_url(profile)

    url = f"{base_url}/{endpoint}"
    if params:
        # Filter out None values
        filtered_params = {k: v for k, v in params.items() if v is not None}
        if filtered_params:
            url += f"?{urlencode(filtered_params)}"

    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            if "errors" in error_data:
                error_message = json.dumps(error_data["errors"])
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Shopify API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Shopify API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Order Actions
# =============================================================================

def list_orders(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List orders from the Shopify store.

    Params:
        status (str): Filter by order status (open, closed, cancelled, any)
        created_at_min (str): Show orders created at or after date (ISO 8601)
        created_at_max (str): Show orders created at or before date (ISO 8601)
        limit (int): Maximum number of orders to return (default: 50, max: 250)
    """
    profile = load_profile(profile_name)

    query_params = {
        "status": params.get("status"),
        "created_at_min": params.get("created_at_min"),
        "created_at_max": params.get("created_at_max"),
        "limit": params.get("limit", 50),
    }

    result = _api_call(profile, "orders.json", params=query_params)

    if result.get("ok") and "data" in result:
        orders = result["data"].get("orders", [])
        return {
            "ok": True,
            "result": {
                "orders": orders,
                "count": len(orders)
            }
        }
    return result


def get_order(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific order.

    Params:
        order_id (str|int): The order ID (required)
    """
    profile = load_profile(profile_name)

    order_id = params.get("order_id")
    if not order_id:
        return {"ok": False, "error": "order_id is required"}

    result = _api_call(profile, f"orders/{order_id}.json")

    if result.get("ok") and "data" in result:
        order = result["data"].get("order", {})
        return {"ok": True, "result": order}
    return result


def create_order(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new order.

    Params:
        line_items (list): List of line items, each with variant_id, quantity
            Example: [{"variant_id": 123, "quantity": 1}]
        customer (dict): Customer info with id or email
            Example: {"id": 123} or {"email": "customer@example.com"}
        shipping_address (dict): Shipping address
            Example: {
                "first_name": "John",
                "last_name": "Doe",
                "address1": "123 Main St",
                "city": "Boston",
                "province": "MA",
                "country": "US",
                "zip": "02101"
            }
        email (str): Customer email (optional if customer provided)
        financial_status (str): paid, pending, etc. (default: pending)
        send_receipt (bool): Send receipt email (default: false)
        send_fulfillment_receipt (bool): Send fulfillment receipt (default: false)
    """
    profile = load_profile(profile_name)

    line_items = params.get("line_items")
    if not line_items:
        return {"ok": False, "error": "line_items is required"}

    order_data: Dict[str, Any] = {
        "line_items": line_items,
    }

    if params.get("customer"):
        order_data["customer"] = params["customer"]

    if params.get("shipping_address"):
        order_data["shipping_address"] = params["shipping_address"]

    if params.get("email"):
        order_data["email"] = params["email"]

    if params.get("financial_status"):
        order_data["financial_status"] = params["financial_status"]

    if params.get("send_receipt") is not None:
        order_data["send_receipt"] = params["send_receipt"]

    if params.get("send_fulfillment_receipt") is not None:
        order_data["send_fulfillment_receipt"] = params["send_fulfillment_receipt"]

    result = _api_call(profile, "orders.json", method="POST", data={"order": order_data})

    if result.get("ok") and "data" in result:
        order = result["data"].get("order", {})
        return {"ok": True, "result": order}
    return result


def update_order(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing order.

    Params:
        order_id (str|int): The order ID (required)
        fields (dict): Fields to update
            Example: {
                "note": "Updated note",
                "email": "newemail@example.com",
                "tags": "tag1, tag2",
                "shipping_address": {...}
            }
    """
    profile = load_profile(profile_name)

    order_id = params.get("order_id")
    if not order_id:
        return {"ok": False, "error": "order_id is required"}

    fields = params.get("fields")
    if not fields:
        return {"ok": False, "error": "fields is required"}

    result = _api_call(
        profile,
        f"orders/{order_id}.json",
        method="PUT",
        data={"order": fields}
    )

    if result.get("ok") and "data" in result:
        order = result["data"].get("order", {})
        return {"ok": True, "result": order}
    return result


# =============================================================================
# Product Actions
# =============================================================================

def list_products(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List products from the Shopify store.

    Params:
        title (str): Filter by product title (partial match)
        vendor (str): Filter by vendor
        product_type (str): Filter by product type
        limit (int): Maximum number of products to return (default: 50, max: 250)
    """
    profile = load_profile(profile_name)

    query_params = {
        "title": params.get("title"),
        "vendor": params.get("vendor"),
        "product_type": params.get("product_type"),
        "limit": params.get("limit", 50),
    }

    result = _api_call(profile, "products.json", params=query_params)

    if result.get("ok") and "data" in result:
        products = result["data"].get("products", [])
        return {
            "ok": True,
            "result": {
                "products": products,
                "count": len(products)
            }
        }
    return result


def get_product(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific product.

    Params:
        product_id (str|int): The product ID (required)
    """
    profile = load_profile(profile_name)

    product_id = params.get("product_id")
    if not product_id:
        return {"ok": False, "error": "product_id is required"}

    result = _api_call(profile, f"products/{product_id}.json")

    if result.get("ok") and "data" in result:
        product = result["data"].get("product", {})
        return {"ok": True, "result": product}
    return result


# =============================================================================
# Inventory Actions
# =============================================================================

def update_inventory(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update inventory level for a specific item at a location.

    Params:
        inventory_item_id (str|int): The inventory item ID (required)
        location_id (str|int): The location ID (required)
        available (int): The new available quantity (required)
    """
    profile = load_profile(profile_name)

    inventory_item_id = params.get("inventory_item_id")
    if not inventory_item_id:
        return {"ok": False, "error": "inventory_item_id is required"}

    location_id = params.get("location_id")
    if not location_id:
        return {"ok": False, "error": "location_id is required"}

    available = params.get("available")
    if available is None:
        return {"ok": False, "error": "available is required"}

    inventory_data = {
        "inventory_item_id": inventory_item_id,
        "location_id": location_id,
        "available": available,
    }

    result = _api_call(
        profile,
        "inventory_levels/set.json",
        method="POST",
        data=inventory_data
    )

    if result.get("ok") and "data" in result:
        inventory_level = result["data"].get("inventory_level", {})
        return {"ok": True, "result": inventory_level}
    return result


# =============================================================================
# Customer Actions
# =============================================================================

def list_customers(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List customers from the Shopify store.

    Params:
        email (str): Filter by email address
        created_at_min (str): Show customers created at or after date (ISO 8601)
        limit (int): Maximum number of customers to return (default: 50, max: 250)
    """
    profile = load_profile(profile_name)

    query_params = {
        "email": params.get("email"),
        "created_at_min": params.get("created_at_min"),
        "limit": params.get("limit", 50),
    }

    result = _api_call(profile, "customers.json", params=query_params)

    if result.get("ok") and "data" in result:
        customers = result["data"].get("customers", [])
        return {
            "ok": True,
            "result": {
                "customers": customers,
                "count": len(customers)
            }
        }
    return result


# =============================================================================
# Fulfillment Actions
# =============================================================================

def create_fulfillment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a fulfillment for an order.

    Params:
        order_id (str|int): The order ID (required)
        tracking_number (str): The tracking number (optional)
        tracking_company (str): The tracking company (optional)
            Examples: "USPS", "UPS", "FedEx", "DHL"
        tracking_url (str): Custom tracking URL (optional)
        notify_customer (bool): Send notification email (default: true)
        line_items (list): Specific line items to fulfill (optional)
            Example: [{"id": 123, "quantity": 1}]
    """
    profile = load_profile(profile_name)

    order_id = params.get("order_id")
    if not order_id:
        return {"ok": False, "error": "order_id is required"}

    # First, get the fulfillment order ID for this order
    fo_result = _api_call(profile, f"orders/{order_id}/fulfillment_orders.json")

    if not fo_result.get("ok"):
        return fo_result

    fulfillment_orders = fo_result.get("data", {}).get("fulfillment_orders", [])
    if not fulfillment_orders:
        return {"ok": False, "error": "No fulfillment orders found for this order"}

    # Get the first open fulfillment order
    fulfillment_order = None
    for fo in fulfillment_orders:
        if fo.get("status") in ("open", "in_progress"):
            fulfillment_order = fo
            break

    if not fulfillment_order:
        return {"ok": False, "error": "No open fulfillment orders available"}

    fulfillment_order_id = fulfillment_order.get("id")

    # Build the fulfillment request
    fulfillment_data: Dict[str, Any] = {
        "fulfillment": {
            "line_items_by_fulfillment_order": [
                {
                    "fulfillment_order_id": fulfillment_order_id,
                }
            ],
        }
    }

    # Add tracking info if provided
    tracking_info: Dict[str, Any] = {}
    if params.get("tracking_number"):
        tracking_info["number"] = params["tracking_number"]
    if params.get("tracking_company"):
        tracking_info["company"] = params["tracking_company"]
    if params.get("tracking_url"):
        tracking_info["url"] = params["tracking_url"]

    if tracking_info:
        fulfillment_data["fulfillment"]["tracking_info"] = tracking_info

    if params.get("notify_customer") is not None:
        fulfillment_data["fulfillment"]["notify_customer"] = params["notify_customer"]

    # If specific line items are provided, include them
    if params.get("line_items"):
        fulfillment_data["fulfillment"]["line_items_by_fulfillment_order"][0]["fulfillment_order_line_items"] = [
            {"id": item.get("id"), "quantity": item.get("quantity")}
            for item in params["line_items"]
        ]

    result = _api_call(
        profile,
        "fulfillments.json",
        method="POST",
        data=fulfillment_data
    )

    if result.get("ok") and "data" in result:
        fulfillment = result["data"].get("fulfillment", {})
        return {"ok": True, "result": fulfillment}
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_orders": list_orders,
    "get_order": get_order,
    "create_order": create_order,
    "update_order": update_order,
    "list_products": list_products,
    "get_product": get_product,
    "update_inventory": update_inventory,
    "list_customers": list_customers,
    "create_fulfillment": create_fulfillment,
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
        logger.info(f"Executing shopify.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
