"""
BigCommerce Controller for TinyHive

A controller for interacting with the BigCommerce Store Management API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "store_hash": "your-store-hash",
    "access_token_env": "BIGCOMMERCE_ACCESS_TOKEN"
}

Or with direct access token (not recommended for production):
{
    "store_hash": "your-store-hash",
    "access_token": "your-access-token"
}

Required Scopes:
---------------
- Products: read/write
- Orders: read/write
- Customers: read/write

API Reference: https://developer.bigcommerce.com/docs/rest-management

Dependencies:
------------
- None (standard library only)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.bigcommerce")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# BigCommerce API base URL
API_BASE = "https://api.bigcommerce.com/stores"

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


def _get_credentials(profile: Dict[str, Any]) -> tuple:
    """
    Extract store_hash and access_token from profile.

    Returns:
        tuple: (store_hash, access_token)
    """
    store_hash = profile.get("store_hash")
    if not store_hash:
        raise ValueError("store_hash is required in profile")

    # Try environment variable first, then direct value
    access_token_env = profile.get("access_token_env")
    if access_token_env:
        access_token = os.environ.get(access_token_env)
        if not access_token:
            raise ValueError(f"Environment variable '{access_token_env}' not set")
    else:
        access_token = profile.get("access_token")
        if not access_token:
            raise ValueError("access_token or access_token_env is required in profile")

    return store_hash, access_token


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    store_hash: str,
    access_token: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated BigCommerce API call.

    Args:
        store_hash: The BigCommerce store hash
        access_token: API access token
        endpoint: API endpoint path (e.g., "/catalog/products")
        method: HTTP method
        data: Request body data (will be JSON encoded)
        params: Query parameters
        timeout: Request timeout in seconds

    Returns:
        dict with 'ok' status and 'result' or 'error'
    """
    url = f"{API_BASE}/{store_hash}/v3{endpoint}"

    if params:
        # Filter out None values
        filtered_params = {k: v for k, v in params.items() if v is not None}
        if filtered_params:
            url += "?" + urlencode(filtered_params)

    headers = {
        "X-Auth-Token": access_token,
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
                return {"ok": True, "result": json.loads(response_body)}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            # BigCommerce returns errors in various formats
            if "errors" in error_data:
                error_message = str(error_data["errors"])
            elif "title" in error_data:
                error_message = error_data.get("title", "") + ": " + str(error_data.get("errors", error_data.get("detail", "")))
            else:
                error_message = error_body[:500]
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("BigCommerce API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in BigCommerce API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Product Actions
# =============================================================================

def list_products(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List products from the catalog.

    Params:
        limit (int): Number of products to return (default: 50, max: 250)
        page (int): Page number (default: 1)
        name (str): Filter by product name (partial match)
        sku (str): Filter by SKU (exact match)
    """
    try:
        profile = load_profile(profile_name)
        store_hash, access_token = _get_credentials(profile)

        query_params = {
            "limit": params.get("limit", 50),
            "page": params.get("page", 1),
        }

        if params.get("name"):
            query_params["name:like"] = params["name"]
        if params.get("sku"):
            query_params["sku"] = params["sku"]

        result = _api_call(store_hash, access_token, "/catalog/products", params=query_params)

        if result.get("ok") and "result" in result:
            data = result["result"]
            products = data.get("data", [])
            meta = data.get("meta", {})
            return {
                "ok": True,
                "data": {
                    "products": [
                        {
                            "id": p.get("id"),
                            "name": p.get("name"),
                            "sku": p.get("sku"),
                            "price": p.get("price"),
                            "type": p.get("type"),
                            "weight": p.get("weight"),
                            "inventory_level": p.get("inventory_level"),
                            "is_visible": p.get("is_visible"),
                            "date_created": p.get("date_created"),
                            "date_modified": p.get("date_modified"),
                        }
                        for p in products
                    ],
                    "pagination": meta.get("pagination", {}),
                }
            }
        return result
    except Exception as e:
        logger.exception("list_products failed")
        return {"ok": False, "error": str(e)}


def get_product(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a single product by ID.

    Params:
        product_id (int): The product ID (required)
    """
    try:
        profile = load_profile(profile_name)
        store_hash, access_token = _get_credentials(profile)

        product_id = params.get("product_id")
        if not product_id:
            return {"ok": False, "error": "product_id is required"}

        result = _api_call(store_hash, access_token, f"/catalog/products/{product_id}")

        if result.get("ok") and "result" in result:
            data = result["result"]
            product = data.get("data", {})
            return {
                "ok": True,
                "data": {
                    "product": product
                }
            }
        return result
    except Exception as e:
        logger.exception("get_product failed")
        return {"ok": False, "error": str(e)}


def create_product(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new product.

    Params:
        name (str): Product name (required)
        type (str): Product type - 'physical' or 'digital' (required)
        weight (float): Product weight (required for physical products)
        price (float): Product price (required)
        sku (str): Product SKU (optional)
        description (str): Product description (optional)
        categories (list): List of category IDs (optional)
    """
    try:
        profile = load_profile(profile_name)
        store_hash, access_token = _get_credentials(profile)

        name = params.get("name")
        product_type = params.get("type")
        weight = params.get("weight")
        price = params.get("price")

        if not name:
            return {"ok": False, "error": "name is required"}
        if not product_type:
            return {"ok": False, "error": "type is required ('physical' or 'digital')"}
        if product_type == "physical" and weight is None:
            return {"ok": False, "error": "weight is required for physical products"}
        if price is None:
            return {"ok": False, "error": "price is required"}

        product_data = {
            "name": name,
            "type": product_type,
            "weight": weight if weight is not None else 0,
            "price": price,
        }

        # Optional fields
        if params.get("sku"):
            product_data["sku"] = params["sku"]
        if params.get("description"):
            product_data["description"] = params["description"]
        if params.get("categories"):
            product_data["categories"] = params["categories"]

        result = _api_call(store_hash, access_token, "/catalog/products", method="POST", data=product_data)

        if result.get("ok") and "result" in result:
            data = result["result"]
            product = data.get("data", {})
            return {
                "ok": True,
                "data": {
                    "product": product
                }
            }
        return result
    except Exception as e:
        logger.exception("create_product failed")
        return {"ok": False, "error": str(e)}


def update_product(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing product.

    Params:
        product_id (int): The product ID (required)
        fields (dict): Fields to update (required)
            - name (str): Product name
            - price (float): Product price
            - sku (str): Product SKU
            - weight (float): Product weight
            - description (str): Product description
            - is_visible (bool): Product visibility
            - inventory_level (int): Inventory level
    """
    try:
        profile = load_profile(profile_name)
        store_hash, access_token = _get_credentials(profile)

        product_id = params.get("product_id")
        fields = params.get("fields")

        if not product_id:
            return {"ok": False, "error": "product_id is required"}
        if not fields or not isinstance(fields, dict):
            return {"ok": False, "error": "fields dict is required"}

        result = _api_call(
            store_hash, access_token,
            f"/catalog/products/{product_id}",
            method="PUT",
            data=fields
        )

        if result.get("ok") and "result" in result:
            data = result["result"]
            product = data.get("data", {})
            return {
                "ok": True,
                "data": {
                    "product": product
                }
            }
        return result
    except Exception as e:
        logger.exception("update_product failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Order Actions
# =============================================================================

def list_orders(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List orders.

    Params:
        status_id (int): Filter by order status ID (optional)
            - 0: Incomplete
            - 1: Pending
            - 2: Shipped
            - 3: Partially Shipped
            - 4: Refunded
            - 5: Cancelled
            - 6: Declined
            - 7: Awaiting Payment
            - 8: Awaiting Pickup
            - 9: Awaiting Shipment
            - 10: Completed
            - 11: Awaiting Fulfillment
            - 12: Manual Verification Required
            - 13: Disputed
            - 14: Partially Refunded
        min_date_created (str): Minimum creation date (RFC 2822 or ISO 8601)
        limit (int): Number of orders to return (default: 50, max: 250)
        page (int): Page number (default: 1)
    """
    try:
        profile = load_profile(profile_name)
        store_hash, access_token = _get_credentials(profile)

        # Orders API uses v2
        query_params = {
            "limit": params.get("limit", 50),
            "page": params.get("page", 1),
        }

        if params.get("status_id") is not None:
            query_params["status_id"] = params["status_id"]
        if params.get("min_date_created"):
            query_params["min_date_created"] = params["min_date_created"]

        # Note: Orders API is v2, not v3
        url = f"{API_BASE}/{store_hash}/v2/orders"

        if query_params:
            filtered_params = {k: v for k, v in query_params.items() if v is not None}
            if filtered_params:
                url += "?" + urlencode(filtered_params)

        headers = {
            "X-Auth-Token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            req = Request(url, headers=headers, method="GET")
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
                response_body = response.read().decode("utf-8")
                orders = json.loads(response_body) if response_body else []

                return {
                    "ok": True,
                    "data": {
                        "orders": [
                            {
                                "id": o.get("id"),
                                "status_id": o.get("status_id"),
                                "status": o.get("status"),
                                "customer_id": o.get("customer_id"),
                                "date_created": o.get("date_created"),
                                "date_modified": o.get("date_modified"),
                                "subtotal_inc_tax": o.get("subtotal_inc_tax"),
                                "total_inc_tax": o.get("total_inc_tax"),
                                "items_total": o.get("items_total"),
                                "payment_method": o.get("payment_method"),
                            }
                            for o in (orders if isinstance(orders, list) else [])
                        ]
                    }
                }
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except Exception as e:
        logger.exception("list_orders failed")
        return {"ok": False, "error": str(e)}


def get_order(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a single order by ID.

    Params:
        order_id (int): The order ID (required)
    """
    try:
        profile = load_profile(profile_name)
        store_hash, access_token = _get_credentials(profile)

        order_id = params.get("order_id")
        if not order_id:
            return {"ok": False, "error": "order_id is required"}

        # Orders API is v2
        url = f"{API_BASE}/{store_hash}/v2/orders/{order_id}"

        headers = {
            "X-Auth-Token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            req = Request(url, headers=headers, method="GET")
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
                response_body = response.read().decode("utf-8")
                order = json.loads(response_body) if response_body else {}

                return {
                    "ok": True,
                    "data": {
                        "order": order
                    }
                }
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except Exception as e:
        logger.exception("get_order failed")
        return {"ok": False, "error": str(e)}


def update_order_status(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an order's status.

    Params:
        order_id (int): The order ID (required)
        status_id (int): The new status ID (required)
            - 0: Incomplete
            - 1: Pending
            - 2: Shipped
            - 3: Partially Shipped
            - 4: Refunded
            - 5: Cancelled
            - 6: Declined
            - 7: Awaiting Payment
            - 8: Awaiting Pickup
            - 9: Awaiting Shipment
            - 10: Completed
            - 11: Awaiting Fulfillment
            - 12: Manual Verification Required
            - 13: Disputed
            - 14: Partially Refunded
    """
    try:
        profile = load_profile(profile_name)
        store_hash, access_token = _get_credentials(profile)

        order_id = params.get("order_id")
        status_id = params.get("status_id")

        if not order_id:
            return {"ok": False, "error": "order_id is required"}
        if status_id is None:
            return {"ok": False, "error": "status_id is required"}

        # Orders API is v2
        url = f"{API_BASE}/{store_hash}/v2/orders/{order_id}"

        headers = {
            "X-Auth-Token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        body = json.dumps({"status_id": status_id}).encode("utf-8")

        try:
            req = Request(url, data=body, headers=headers, method="PUT")
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
                response_body = response.read().decode("utf-8")
                order = json.loads(response_body) if response_body else {}

                return {
                    "ok": True,
                    "data": {
                        "order": order
                    }
                }
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except Exception as e:
        logger.exception("update_order_status failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Customer Actions
# =============================================================================

def list_customers(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List customers.

    Params:
        email (str): Filter by email address (optional)
        name (str): Filter by name (partial match) (optional)
        limit (int): Number of customers to return (default: 50, max: 250)
        page (int): Page number (default: 1)
    """
    try:
        profile = load_profile(profile_name)
        store_hash, access_token = _get_credentials(profile)

        query_params = {
            "limit": params.get("limit", 50),
            "page": params.get("page", 1),
        }

        if params.get("email"):
            query_params["email:in"] = params["email"]
        if params.get("name"):
            query_params["name:like"] = params["name"]

        result = _api_call(store_hash, access_token, "/customers", params=query_params)

        if result.get("ok") and "result" in result:
            data = result["result"]
            customers = data.get("data", [])
            meta = data.get("meta", {})
            return {
                "ok": True,
                "data": {
                    "customers": [
                        {
                            "id": c.get("id"),
                            "email": c.get("email"),
                            "first_name": c.get("first_name"),
                            "last_name": c.get("last_name"),
                            "company": c.get("company"),
                            "phone": c.get("phone"),
                            "date_created": c.get("date_created"),
                            "date_modified": c.get("date_modified"),
                            "customer_group_id": c.get("customer_group_id"),
                        }
                        for c in customers
                    ],
                    "pagination": meta.get("pagination", {}),
                }
            }
        return result
    except Exception as e:
        logger.exception("list_customers failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_products": list_products,
    "get_product": get_product,
    "create_product": create_product,
    "update_product": update_product,
    "list_orders": list_orders,
    "get_order": get_order,
    "update_order_status": update_order_status,
    "list_customers": list_customers,
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

    logger.info(f"Executing bigcommerce.{profile}.{action}")
    return ACTIONS[action](profile, params)
