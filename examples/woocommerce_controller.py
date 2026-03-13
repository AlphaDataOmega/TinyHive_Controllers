"""
WooCommerce Controller for TinyHive

A controller for WooCommerce REST API integration using OAuth 1.0a authentication.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "store_url": "https://mystore.com",
    "api_version": "wc/v3"
}

Environment Variables:
----------------------
- WC_CONSUMER_KEY: WooCommerce REST API consumer key
- WC_CONSUMER_SECRET: WooCommerce REST API consumer secret

Or use profile-specific env var names:
{
    "store_url": "https://mystore.com",
    "consumer_key_env": "MYSTORE_WC_KEY",
    "consumer_secret_env": "MYSTORE_WC_SECRET"
}

Method IDs:
----------
  controller.woocommerce.{profile}.list_orders
  controller.woocommerce.{profile}.get_order
  controller.woocommerce.{profile}.update_order
  controller.woocommerce.{profile}.create_order
  controller.woocommerce.{profile}.list_products
  controller.woocommerce.{profile}.get_product
  controller.woocommerce.{profile}.update_product
  controller.woocommerce.{profile}.list_customers

Dependencies:
------------
None (standard library only)
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import random
import string
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger("tinyhive.controller.woocommerce")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

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
    """Get consumer key and secret from environment variables."""
    key_env = profile.get("consumer_key_env", "WC_CONSUMER_KEY")
    secret_env = profile.get("consumer_secret_env", "WC_CONSUMER_SECRET")

    consumer_key = os.environ.get(key_env)
    consumer_secret = os.environ.get(secret_env)

    if not consumer_key:
        raise ValueError(f"Missing environment variable: {key_env}")
    if not consumer_secret:
        raise ValueError(f"Missing environment variable: {secret_env}")

    return consumer_key, consumer_secret


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the WooCommerce REST API base URL."""
    store_url = profile.get("store_url", "").rstrip("/")
    if not store_url:
        raise ValueError("store_url is required in profile")

    api_version = profile.get("api_version", "wc/v3")
    return f"{store_url}/wp-json/{api_version}"


# =============================================================================
# OAuth 1.0a Signing
# =============================================================================

def _generate_nonce(length: int = 32) -> str:
    """Generate a random nonce for OAuth."""
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def _percent_encode(value: str) -> str:
    """Percent encode a string according to OAuth spec."""
    return quote(str(value), safe="")


def _create_signature_base_string(
    method: str,
    url: str,
    params: Dict[str, str]
) -> str:
    """Create the OAuth signature base string."""
    # Sort parameters and encode
    sorted_params = sorted(params.items())
    param_string = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}"
        for k, v in sorted_params
    )

    # Parse URL to get base URL without query string
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    # Create signature base string
    return "&".join([
        method.upper(),
        _percent_encode(base_url),
        _percent_encode(param_string)
    ])


def _create_oauth_signature(
    method: str,
    url: str,
    params: Dict[str, str],
    consumer_secret: str
) -> str:
    """Create OAuth 1.0a HMAC-SHA1 signature."""
    base_string = _create_signature_base_string(method, url, params)

    # Key is consumer_secret& (no token secret for WooCommerce)
    signing_key = f"{_percent_encode(consumer_secret)}&"

    signature = hmac.new(
        signing_key.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha1
    ).digest()

    return base64.b64encode(signature).decode("utf-8")


def _build_oauth_params(consumer_key: str) -> Dict[str, str]:
    """Build OAuth 1.0a parameters."""
    return {
        "oauth_consumer_key": consumer_key,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_nonce": _generate_nonce(),
        "oauth_version": "1.0"
    }


# =============================================================================
# API Call Helper
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    endpoint: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated WooCommerce API call.

    For HTTPS URLs, uses query string authentication (simpler and secure).
    For HTTP URLs, uses OAuth 1.0a header authentication.
    """
    consumer_key, consumer_secret = _get_credentials(profile)
    base_url = _get_base_url(profile)
    url = f"{base_url}/{endpoint.lstrip('/')}"

    # Parse existing query params from URL
    parsed = urlparse(url)
    query_params = {}
    if parsed.query:
        query_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    # Add any additional params
    if params:
        # Convert all param values to strings
        for k, v in params.items():
            if v is not None:
                query_params[k] = str(v)

    # Build clean URL without query string
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "TinyHive-WooCommerce-Controller/1.0"
    }

    # Use HTTPS query string auth (simpler and recommended for HTTPS)
    if parsed.scheme == "https":
        # Add credentials to query params
        query_params["consumer_key"] = consumer_key
        query_params["consumer_secret"] = consumer_secret

        if query_params:
            url = f"{clean_url}?{urlencode(query_params)}"
        else:
            url = clean_url
    else:
        # Use OAuth 1.0a for HTTP
        oauth_params = _build_oauth_params(consumer_key)

        # Combine OAuth params with query params for signature
        all_params = {**oauth_params, **query_params}

        # Create signature
        signature = _create_oauth_signature(
            method, clean_url, all_params, consumer_secret
        )
        oauth_params["oauth_signature"] = signature

        # Build Authorization header
        auth_header = "OAuth " + ", ".join(
            f'{_percent_encode(k)}="{_percent_encode(v)}"'
            for k, v in sorted(oauth_params.items())
        )
        headers["Authorization"] = auth_header

        # Build URL with query params
        if query_params:
            url = f"{clean_url}?{urlencode(query_params)}"
        else:
            url = clean_url

    # Prepare request body
    request_data = None
    if data is not None:
        request_data = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=request_data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {}}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
            error_code = error_data.get("code", "unknown")
        except json.JSONDecodeError:
            error_message = error_body[:500]
            error_code = "unknown"

        logger.error("WooCommerce API error %d: %s", e.code, error_message)
        return {
            "ok": False,
            "error": f"HTTP {e.code}: {error_message}",
            "code": error_code
        }

    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}

    except Exception as e:
        logger.exception("Unexpected error in WooCommerce API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Order Actions
# =============================================================================

def list_orders(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List orders from WooCommerce.

    Params:
        status (str): Filter by order status (pending, processing, on-hold,
                      completed, cancelled, refunded, failed, trash)
        per_page (int): Number of orders per page (default: 10, max: 100)
        page (int): Page number (default: 1)
        after (str): Limit to orders after this date (ISO 8601)
        before (str): Limit to orders before this date (ISO 8601)
        customer (int): Filter by customer ID
    """
    try:
        profile = load_profile(profile_name)

        query_params = {}
        if params.get("status"):
            query_params["status"] = params["status"]
        if params.get("per_page"):
            query_params["per_page"] = min(int(params["per_page"]), 100)
        if params.get("page"):
            query_params["page"] = int(params["page"])
        if params.get("after"):
            query_params["after"] = params["after"]
        if params.get("before"):
            query_params["before"] = params["before"]
        if params.get("customer"):
            query_params["customer"] = int(params["customer"])

        result = _api_call(profile, "orders", params=query_params)

        if result.get("ok") and "data" in result:
            orders = result["data"]
            return {
                "ok": True,
                "result": {
                    "orders": [
                        {
                            "id": o.get("id"),
                            "number": o.get("number"),
                            "status": o.get("status"),
                            "date_created": o.get("date_created"),
                            "total": o.get("total"),
                            "currency": o.get("currency"),
                            "customer_id": o.get("customer_id"),
                            "billing": o.get("billing"),
                            "line_items_count": len(o.get("line_items", []))
                        }
                        for o in orders
                    ],
                    "count": len(orders)
                }
            }
        return result

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

        order_id = params.get("order_id")
        if not order_id:
            return {"ok": False, "error": "order_id is required"}

        result = _api_call(profile, f"orders/{order_id}")

        if result.get("ok") and "data" in result:
            return {"ok": True, "result": result["data"]}
        return result

    except Exception as e:
        logger.exception("get_order failed")
        return {"ok": False, "error": str(e)}


def update_order(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing order.

    Params:
        order_id (int): The order ID (required)
        status (str): New order status
        meta_data (list): List of meta data objects [{key, value}]
        billing (dict): Billing address fields
        shipping (dict): Shipping address fields
        customer_note (str): Note for the customer
    """
    try:
        profile = load_profile(profile_name)

        order_id = params.get("order_id")
        if not order_id:
            return {"ok": False, "error": "order_id is required"}

        update_data = {}
        if params.get("status"):
            update_data["status"] = params["status"]
        if params.get("meta_data"):
            update_data["meta_data"] = params["meta_data"]
        if params.get("billing"):
            update_data["billing"] = params["billing"]
        if params.get("shipping"):
            update_data["shipping"] = params["shipping"]
        if params.get("customer_note"):
            update_data["customer_note"] = params["customer_note"]

        if not update_data:
            return {"ok": False, "error": "No update fields provided"}

        result = _api_call(
            profile,
            f"orders/{order_id}",
            method="PUT",
            data=update_data
        )

        if result.get("ok") and "data" in result:
            return {"ok": True, "result": result["data"]}
        return result

    except Exception as e:
        logger.exception("update_order failed")
        return {"ok": False, "error": str(e)}


def create_order(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new order.

    Params:
        customer_id (int): Customer ID (0 for guest)
        line_items (list): List of line items (required)
            Each item: {product_id, quantity, variation_id (optional)}
        billing (dict): Billing address
            {first_name, last_name, address_1, city, state, postcode, country, email, phone}
        shipping (dict): Shipping address
            {first_name, last_name, address_1, city, state, postcode, country}
        payment_method (str): Payment method ID
        payment_method_title (str): Payment method title
        set_paid (bool): Whether to mark as paid (default: false)
        status (str): Order status (default: pending)
        shipping_lines (list): Shipping lines [{method_id, method_title, total}]
        coupon_lines (list): Coupon lines [{code}]
        meta_data (list): Meta data [{key, value}]
    """
    try:
        profile = load_profile(profile_name)

        line_items = params.get("line_items")
        if not line_items:
            return {"ok": False, "error": "line_items is required"}

        order_data = {
            "line_items": line_items
        }

        # Optional fields
        if params.get("customer_id") is not None:
            order_data["customer_id"] = int(params["customer_id"])
        if params.get("billing"):
            order_data["billing"] = params["billing"]
        if params.get("shipping"):
            order_data["shipping"] = params["shipping"]
        if params.get("payment_method"):
            order_data["payment_method"] = params["payment_method"]
        if params.get("payment_method_title"):
            order_data["payment_method_title"] = params["payment_method_title"]
        if params.get("set_paid") is not None:
            order_data["set_paid"] = bool(params["set_paid"])
        if params.get("status"):
            order_data["status"] = params["status"]
        if params.get("shipping_lines"):
            order_data["shipping_lines"] = params["shipping_lines"]
        if params.get("coupon_lines"):
            order_data["coupon_lines"] = params["coupon_lines"]
        if params.get("meta_data"):
            order_data["meta_data"] = params["meta_data"]

        result = _api_call(
            profile,
            "orders",
            method="POST",
            data=order_data
        )

        if result.get("ok") and "data" in result:
            return {"ok": True, "result": result["data"]}
        return result

    except Exception as e:
        logger.exception("create_order failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Product Actions
# =============================================================================

def list_products(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List products from WooCommerce.

    Params:
        category (int): Filter by category ID
        status (str): Filter by status (draft, pending, private, publish)
        per_page (int): Number of products per page (default: 10, max: 100)
        page (int): Page number (default: 1)
        search (str): Search products by term
        sku (str): Filter by SKU
        tag (int): Filter by tag ID
        on_sale (bool): Filter by on sale status
        stock_status (str): Filter by stock status (instock, outofstock, onbackorder)
    """
    try:
        profile = load_profile(profile_name)

        query_params = {}
        if params.get("category"):
            query_params["category"] = int(params["category"])
        if params.get("status"):
            query_params["status"] = params["status"]
        if params.get("per_page"):
            query_params["per_page"] = min(int(params["per_page"]), 100)
        if params.get("page"):
            query_params["page"] = int(params["page"])
        if params.get("search"):
            query_params["search"] = params["search"]
        if params.get("sku"):
            query_params["sku"] = params["sku"]
        if params.get("tag"):
            query_params["tag"] = int(params["tag"])
        if params.get("on_sale") is not None:
            query_params["on_sale"] = str(params["on_sale"]).lower()
        if params.get("stock_status"):
            query_params["stock_status"] = params["stock_status"]

        result = _api_call(profile, "products", params=query_params)

        if result.get("ok") and "data" in result:
            products = result["data"]
            return {
                "ok": True,
                "result": {
                    "products": [
                        {
                            "id": p.get("id"),
                            "name": p.get("name"),
                            "slug": p.get("slug"),
                            "status": p.get("status"),
                            "type": p.get("type"),
                            "sku": p.get("sku"),
                            "price": p.get("price"),
                            "regular_price": p.get("regular_price"),
                            "sale_price": p.get("sale_price"),
                            "stock_quantity": p.get("stock_quantity"),
                            "stock_status": p.get("stock_status"),
                            "categories": [
                                {"id": c.get("id"), "name": c.get("name")}
                                for c in p.get("categories", [])
                            ]
                        }
                        for p in products
                    ],
                    "count": len(products)
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

        product_id = params.get("product_id")
        if not product_id:
            return {"ok": False, "error": "product_id is required"}

        result = _api_call(profile, f"products/{product_id}")

        if result.get("ok") and "data" in result:
            return {"ok": True, "result": result["data"]}
        return result

    except Exception as e:
        logger.exception("get_product failed")
        return {"ok": False, "error": str(e)}


def update_product(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing product.

    Params:
        product_id (int): The product ID (required)
        stock_quantity (int): New stock quantity
        price (str): New regular price
        sale_price (str): New sale price (empty string to remove)
        status (str): Product status (draft, pending, private, publish)
        name (str): Product name
        description (str): Product description
        short_description (str): Short description
        sku (str): SKU
        manage_stock (bool): Enable stock management
        stock_status (str): Stock status (instock, outofstock, onbackorder)
        categories (list): Category IDs [{id: 1}, {id: 2}]
        tags (list): Tag IDs [{id: 1}, {id: 2}]
        meta_data (list): Meta data [{key, value}]
    """
    try:
        profile = load_profile(profile_name)

        product_id = params.get("product_id")
        if not product_id:
            return {"ok": False, "error": "product_id is required"}

        update_data = {}
        if params.get("stock_quantity") is not None:
            update_data["stock_quantity"] = int(params["stock_quantity"])
        if params.get("price") is not None:
            update_data["regular_price"] = str(params["price"])
        if params.get("sale_price") is not None:
            update_data["sale_price"] = str(params["sale_price"])
        if params.get("status"):
            update_data["status"] = params["status"]
        if params.get("name"):
            update_data["name"] = params["name"]
        if params.get("description"):
            update_data["description"] = params["description"]
        if params.get("short_description"):
            update_data["short_description"] = params["short_description"]
        if params.get("sku"):
            update_data["sku"] = params["sku"]
        if params.get("manage_stock") is not None:
            update_data["manage_stock"] = bool(params["manage_stock"])
        if params.get("stock_status"):
            update_data["stock_status"] = params["stock_status"]
        if params.get("categories"):
            update_data["categories"] = params["categories"]
        if params.get("tags"):
            update_data["tags"] = params["tags"]
        if params.get("meta_data"):
            update_data["meta_data"] = params["meta_data"]

        if not update_data:
            return {"ok": False, "error": "No update fields provided"}

        result = _api_call(
            profile,
            f"products/{product_id}",
            method="PUT",
            data=update_data
        )

        if result.get("ok") and "data" in result:
            return {"ok": True, "result": result["data"]}
        return result

    except Exception as e:
        logger.exception("update_product failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Customer Actions
# =============================================================================

def list_customers(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List customers from WooCommerce.

    Params:
        per_page (int): Number of customers per page (default: 10, max: 100)
        page (int): Page number (default: 1)
        email (str): Filter by email address
        search (str): Search customers
        role (str): Filter by role (all, administrator, customer, etc.)
        orderby (str): Sort by (id, include, name, registered_date)
        order (str): Sort order (asc, desc)
    """
    try:
        profile = load_profile(profile_name)

        query_params = {}
        if params.get("per_page"):
            query_params["per_page"] = min(int(params["per_page"]), 100)
        if params.get("page"):
            query_params["page"] = int(params["page"])
        if params.get("email"):
            query_params["email"] = params["email"]
        if params.get("search"):
            query_params["search"] = params["search"]
        if params.get("role"):
            query_params["role"] = params["role"]
        if params.get("orderby"):
            query_params["orderby"] = params["orderby"]
        if params.get("order"):
            query_params["order"] = params["order"]

        result = _api_call(profile, "customers", params=query_params)

        if result.get("ok") and "data" in result:
            customers = result["data"]
            return {
                "ok": True,
                "result": {
                    "customers": [
                        {
                            "id": c.get("id"),
                            "email": c.get("email"),
                            "first_name": c.get("first_name"),
                            "last_name": c.get("last_name"),
                            "username": c.get("username"),
                            "role": c.get("role"),
                            "date_created": c.get("date_created"),
                            "billing": c.get("billing"),
                            "shipping": c.get("shipping"),
                            "orders_count": c.get("orders_count"),
                            "total_spent": c.get("total_spent")
                        }
                        for c in customers
                    ],
                    "count": len(customers)
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
    "list_orders": list_orders,
    "get_order": get_order,
    "update_order": update_order,
    "create_order": create_order,
    "list_products": list_products,
    "get_product": get_product,
    "update_product": update_product,
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
        return {
            "ok": False,
            "error": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"
        }

    logger.info(f"Executing woocommerce.{profile}.{action}")
    return ACTIONS[action](profile, params)
