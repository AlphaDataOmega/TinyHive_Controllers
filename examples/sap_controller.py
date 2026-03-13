"""
SAP Business One Controller for TinyHive

A controller for SAP Business One Service Layer API integration.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

SAP Business One profile:
{
    "server": "sap-server.example.com",
    "company_db": "SBODemoUS",
    "ssl_verify": true
}

Environment Variables:
----------------------
- SAP_B1_USERNAME: Service Layer username
- SAP_B1_PASSWORD: Service Layer password

Or use profile-specific environment variables:
- SAP_B1_{PROFILE}_USERNAME
- SAP_B1_{PROFILE}_PASSWORD

Base URL: https://{server}:50000/b1s/v1

Method IDs:
-----------
  controller.sap.{profile}.login
  controller.sap.{profile}.list_business_partners
  controller.sap.{profile}.get_business_partner
  controller.sap.{profile}.create_business_partner
  controller.sap.{profile}.list_orders
  controller.sap.{profile}.create_order
  controller.sap.{profile}.list_items
  controller.sap.{profile}.get_stock

Dependencies:
-------------
- None (standard library only)
"""

import json
import logging
import os
import ssl
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.sap")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Session cache: profile_name -> {"cookies": CookieJar, "session_id": str}
_session_cache: Dict[str, Dict[str, Any]] = {}

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


def _get_credentials(profile_name: str) -> tuple:
    """Get username and password from environment variables."""
    # Try profile-specific env vars first
    profile_upper = profile_name.upper().replace("-", "_")
    username = os.environ.get(f"SAP_B1_{profile_upper}_USERNAME")
    password = os.environ.get(f"SAP_B1_{profile_upper}_PASSWORD")

    # Fall back to generic env vars
    if not username:
        username = os.environ.get("SAP_B1_USERNAME")
    if not password:
        password = os.environ.get("SAP_B1_PASSWORD")

    if not username or not password:
        raise ValueError(
            f"Missing credentials. Set SAP_B1_USERNAME and SAP_B1_PASSWORD "
            f"or SAP_B1_{profile_upper}_USERNAME and SAP_B1_{profile_upper}_PASSWORD"
        )

    return username, password


def _get_base_url(profile: Dict[str, Any]) -> str:
    """Get the Service Layer base URL from profile."""
    server = profile.get("server")
    if not server:
        raise ValueError("Profile must specify 'server'")
    port = profile.get("port", 50000)
    return f"https://{server}:{port}/b1s/v1"


# =============================================================================
# Session Management
# =============================================================================

def _login(profile_name: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Authenticate with SAP Business One Service Layer and establish session.

    Returns session info including cookies for subsequent requests.
    """
    username, password = _get_credentials(profile_name)
    base_url = _get_base_url(profile)
    company_db = profile.get("company_db")

    if not company_db:
        raise ValueError("Profile must specify 'company_db'")

    login_url = f"{base_url}/Login"
    login_payload = {
        "CompanyDB": company_db,
        "UserName": username,
        "Password": password
    }

    # Create cookie jar for session management
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))

    # SSL context
    ssl_context = None
    if not profile.get("ssl_verify", True):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    data = json.dumps(login_payload).encode("utf-8")
    req = Request(login_url, data=data, headers=headers, method="POST")

    try:
        if ssl_context:
            response = urlopen(req, timeout=DEFAULT_TIMEOUT, context=ssl_context)
        else:
            response = opener.open(req, timeout=DEFAULT_TIMEOUT)

        response_body = response.read().decode("utf-8")
        result = json.loads(response_body) if response_body else {}

        # Extract session ID from response
        session_id = result.get("SessionId", "")

        # Cache the session
        _session_cache[profile_name] = {
            "cookies": cookie_jar,
            "session_id": session_id,
            "base_url": base_url,
            "ssl_verify": profile.get("ssl_verify", True)
        }

        logger.info(f"Login successful for profile {profile_name}")
        return {"ok": True, "result": {"session_id": session_id, "session_timeout": result.get("SessionTimeout")}}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("error", {}).get("message", {}).get("value", error_body[:500])
        except (json.JSONDecodeError, AttributeError):
            error_message = error_body[:500]
        logger.error("SAP login error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error during login: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error during SAP login")
        return {"ok": False, "error": str(e)}


def _logout(profile_name: str) -> Dict[str, Any]:
    """Logout from SAP Business One Service Layer and clear session."""
    session = _session_cache.get(profile_name)
    if not session:
        return {"ok": True, "result": {"message": "No active session"}}

    base_url = session.get("base_url")
    session_id = session.get("session_id")

    if base_url and session_id:
        logout_url = f"{base_url}/Logout"
        try:
            result = _api_call(profile_name, logout_url, method="POST")
            logger.info(f"Logout successful for profile {profile_name}")
        except Exception as e:
            logger.warning(f"Logout request failed: {e}")

    # Clear session cache
    if profile_name in _session_cache:
        del _session_cache[profile_name]

    return {"ok": True, "result": {"message": "Logged out"}}


def _ensure_session(profile_name: str) -> Dict[str, Any]:
    """Ensure we have a valid session, logging in if necessary."""
    if profile_name not in _session_cache:
        profile = load_profile(profile_name)
        result = _login(profile_name, profile)
        if not result["ok"]:
            return result
    return {"ok": True}


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    profile_name: str,
    url: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated SAP Service Layer API call."""
    session = _session_cache.get(profile_name)
    if not session:
        return {"ok": False, "error": "No active session. Call login first."}

    session_id = session.get("session_id")
    ssl_verify = session.get("ssl_verify", True)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Cookie": f"B1SESSION={session_id}"
    }

    # SSL context
    ssl_context = None
    if not ssl_verify:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)

        if ssl_context:
            response = urlopen(req, timeout=timeout, context=ssl_context)
        else:
            response = urlopen(req, timeout=timeout)

        response_body = response.read().decode("utf-8")

        if response_body:
            result = json.loads(response_body)
            return {"ok": True, "result": result}
        return {"ok": True, "result": {"status": "success"}}

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("error", {}).get("message", {}).get("value", error_body[:500])
        except (json.JSONDecodeError, AttributeError, TypeError):
            error_message = error_body[:500]
        logger.error("SAP API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in SAP API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Actions
# =============================================================================

def login(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Authenticate with SAP Business One Service Layer.

    Establishes a session for subsequent API calls. The session is cached
    and reused for other actions.

    Params:
        (none required - credentials from environment variables)

    Returns:
        session_id: The session identifier
        session_timeout: Session timeout in minutes
    """
    try:
        profile = load_profile(profile_name)
        return _login(profile_name, profile)
    except Exception as e:
        logger.exception("Login failed")
        return {"ok": False, "error": str(e)}


def list_business_partners(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List business partners from SAP Business One.

    Params:
        filter (str): OData filter expression (e.g., "CardType eq 'cCustomer'")
        select (str): Comma-separated fields to return (e.g., "CardCode,CardName")
        top (int): Maximum number of records to return (default: 20)
        skip (int): Number of records to skip for pagination
        orderby (str): Field to order by (e.g., "CardName asc")

    Returns:
        value: List of business partner records
    """
    try:
        session_result = _ensure_session(profile_name)
        if not session_result["ok"]:
            return session_result

        session = _session_cache[profile_name]
        base_url = session["base_url"]

        # Build query parameters
        query_params = []

        if params.get("filter"):
            query_params.append(f"$filter={quote(params['filter'], safe='')}")

        if params.get("select"):
            query_params.append(f"$select={quote(params['select'], safe='')}")

        top = params.get("top", 20)
        query_params.append(f"$top={top}")

        if params.get("skip"):
            query_params.append(f"$skip={params['skip']}")

        if params.get("orderby"):
            query_params.append(f"$orderby={quote(params['orderby'], safe='')}")

        url = f"{base_url}/BusinessPartners"
        if query_params:
            url += "?" + "&".join(query_params)

        result = _api_call(profile_name, url)

        if result.get("ok") and "result" in result:
            data = result["result"]
            return {
                "ok": True,
                "data": data.get("value", []),
                "count": len(data.get("value", []))
            }
        return result

    except Exception as e:
        logger.exception("list_business_partners failed")
        return {"ok": False, "error": str(e)}


def get_business_partner(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a single business partner by CardCode.

    Params:
        CardCode (str): Business partner code (required)
        select (str): Comma-separated fields to return (optional)

    Returns:
        Business partner record
    """
    try:
        session_result = _ensure_session(profile_name)
        if not session_result["ok"]:
            return session_result

        card_code = params.get("CardCode")
        if not card_code:
            return {"ok": False, "error": "CardCode is required"}

        session = _session_cache[profile_name]
        base_url = session["base_url"]

        # Build URL with quoted CardCode
        url = f"{base_url}/BusinessPartners('{quote(card_code, safe='')}')"

        if params.get("select"):
            url += f"?$select={quote(params['select'], safe='')}"

        result = _api_call(profile_name, url)

        if result.get("ok") and "result" in result:
            return {"ok": True, "data": result["result"]}
        return result

    except Exception as e:
        logger.exception("get_business_partner failed")
        return {"ok": False, "error": str(e)}


def create_business_partner(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new business partner.

    Params:
        CardCode (str): Business partner code (optional, auto-generated if not provided)
        CardName (str): Business partner name (required)
        CardType (str): Type - 'cCustomer', 'cSupplier', or 'cLead' (required)
        fields (dict): Additional fields to set on the business partner

    Common fields:
        - GroupCode: Business partner group
        - Phone1, Phone2: Phone numbers
        - Cellular: Mobile phone
        - Fax: Fax number
        - EmailAddress: Email
        - ContactPerson: Primary contact
        - BilltoDefault: Default billing address
        - ShipToDefault: Default shipping address

    Returns:
        Created business partner record
    """
    try:
        session_result = _ensure_session(profile_name)
        if not session_result["ok"]:
            return session_result

        card_name = params.get("CardName")
        card_type = params.get("CardType")

        if not card_name:
            return {"ok": False, "error": "CardName is required"}
        if not card_type:
            return {"ok": False, "error": "CardType is required"}

        session = _session_cache[profile_name]
        base_url = session["base_url"]

        # Build the business partner payload
        bp_data = {
            "CardName": card_name,
            "CardType": card_type
        }

        # Add CardCode if provided
        if params.get("CardCode"):
            bp_data["CardCode"] = params["CardCode"]

        # Merge additional fields
        fields = params.get("fields", {})
        bp_data.update(fields)

        url = f"{base_url}/BusinessPartners"
        result = _api_call(profile_name, url, method="POST", data=bp_data)

        if result.get("ok") and "result" in result:
            return {"ok": True, "data": result["result"]}
        return result

    except Exception as e:
        logger.exception("create_business_partner failed")
        return {"ok": False, "error": str(e)}


def list_orders(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List sales orders from SAP Business One.

    Params:
        filter (str): OData filter expression (e.g., "DocStatus eq 'bost_Open'")
        select (str): Comma-separated fields to return
        top (int): Maximum number of records to return (default: 20)
        skip (int): Number of records to skip for pagination
        orderby (str): Field to order by (e.g., "DocEntry desc")

    Common filter examples:
        - "DocStatus eq 'bost_Open'" - Open orders
        - "CardCode eq 'C20000'" - Orders for specific customer
        - "DocDate ge '2024-01-01'" - Orders from date

    Returns:
        value: List of sales order records
    """
    try:
        session_result = _ensure_session(profile_name)
        if not session_result["ok"]:
            return session_result

        session = _session_cache[profile_name]
        base_url = session["base_url"]

        # Build query parameters
        query_params = []

        if params.get("filter"):
            query_params.append(f"$filter={quote(params['filter'], safe='')}")

        if params.get("select"):
            query_params.append(f"$select={quote(params['select'], safe='')}")

        top = params.get("top", 20)
        query_params.append(f"$top={top}")

        if params.get("skip"):
            query_params.append(f"$skip={params['skip']}")

        if params.get("orderby"):
            query_params.append(f"$orderby={quote(params['orderby'], safe='')}")

        url = f"{base_url}/Orders"
        if query_params:
            url += "?" + "&".join(query_params)

        result = _api_call(profile_name, url)

        if result.get("ok") and "result" in result:
            data = result["result"]
            return {
                "ok": True,
                "data": data.get("value", []),
                "count": len(data.get("value", []))
            }
        return result

    except Exception as e:
        logger.exception("list_orders failed")
        return {"ok": False, "error": str(e)}


def create_order(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new sales order.

    Params:
        CardCode (str): Customer/business partner code (required)
        DocumentLines (list): List of order line items (required)
        DocDate (str): Document date (YYYY-MM-DD, default: today)
        DocDueDate (str): Due date (YYYY-MM-DD)
        fields (dict): Additional header fields

    DocumentLines format:
        [
            {
                "ItemCode": "A00001",
                "Quantity": 10,
                "UnitPrice": 100.00,
                "WarehouseCode": "01"
            },
            ...
        ]

    Common header fields:
        - Comments: Order comments
        - SalesPersonCode: Sales rep code
        - ShipToCode: Shipping address code
        - PayToCode: Billing address code

    Returns:
        Created sales order record
    """
    try:
        session_result = _ensure_session(profile_name)
        if not session_result["ok"]:
            return session_result

        card_code = params.get("CardCode")
        document_lines = params.get("DocumentLines")

        if not card_code:
            return {"ok": False, "error": "CardCode is required"}
        if not document_lines:
            return {"ok": False, "error": "DocumentLines is required"}
        if not isinstance(document_lines, list):
            return {"ok": False, "error": "DocumentLines must be a list"}

        session = _session_cache[profile_name]
        base_url = session["base_url"]

        # Build the order payload
        order_data = {
            "CardCode": card_code,
            "DocumentLines": document_lines
        }

        # Add optional date fields
        if params.get("DocDate"):
            order_data["DocDate"] = params["DocDate"]
        if params.get("DocDueDate"):
            order_data["DocDueDate"] = params["DocDueDate"]

        # Merge additional fields
        fields = params.get("fields", {})
        order_data.update(fields)

        url = f"{base_url}/Orders"
        result = _api_call(profile_name, url, method="POST", data=order_data)

        if result.get("ok") and "result" in result:
            return {"ok": True, "data": result["result"]}
        return result

    except Exception as e:
        logger.exception("create_order failed")
        return {"ok": False, "error": str(e)}


def list_items(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List items (products) from SAP Business One.

    Params:
        filter (str): OData filter expression (e.g., "ItemType eq 'itItems'")
        select (str): Comma-separated fields to return
        top (int): Maximum number of records to return (default: 20)
        skip (int): Number of records to skip for pagination
        orderby (str): Field to order by

    Common filter examples:
        - "ItemType eq 'itItems'" - Regular items only
        - "SalesItem eq 'tYES'" - Sales items
        - "InventoryItem eq 'tYES'" - Inventory items
        - "Valid eq 'tYES'" - Active items

    Returns:
        value: List of item records
    """
    try:
        session_result = _ensure_session(profile_name)
        if not session_result["ok"]:
            return session_result

        session = _session_cache[profile_name]
        base_url = session["base_url"]

        # Build query parameters
        query_params = []

        if params.get("filter"):
            query_params.append(f"$filter={quote(params['filter'], safe='')}")

        if params.get("select"):
            query_params.append(f"$select={quote(params['select'], safe='')}")

        top = params.get("top", 20)
        query_params.append(f"$top={top}")

        if params.get("skip"):
            query_params.append(f"$skip={params['skip']}")

        if params.get("orderby"):
            query_params.append(f"$orderby={quote(params['orderby'], safe='')}")

        url = f"{base_url}/Items"
        if query_params:
            url += "?" + "&".join(query_params)

        result = _api_call(profile_name, url)

        if result.get("ok") and "result" in result:
            data = result["result"]
            return {
                "ok": True,
                "data": data.get("value", []),
                "count": len(data.get("value", []))
            }
        return result

    except Exception as e:
        logger.exception("list_items failed")
        return {"ok": False, "error": str(e)}


def get_stock(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get stock/inventory information for an item.

    Params:
        ItemCode (str): Item code (required)
        WarehouseCode (str): Specific warehouse code (optional)

    Returns:
        Stock information including quantity on hand per warehouse
    """
    try:
        session_result = _ensure_session(profile_name)
        if not session_result["ok"]:
            return session_result

        item_code = params.get("ItemCode")
        if not item_code:
            return {"ok": False, "error": "ItemCode is required"}

        session = _session_cache[profile_name]
        base_url = session["base_url"]

        warehouse_code = params.get("WarehouseCode")

        if warehouse_code:
            # Get stock for specific warehouse from ItemWarehouseInfoCollection
            url = f"{base_url}/Items('{quote(item_code, safe='')}')?$select=ItemCode,ItemName,ItemWarehouseInfoCollection"
            result = _api_call(profile_name, url)

            if result.get("ok") and "result" in result:
                item_data = result["result"]
                warehouse_info = item_data.get("ItemWarehouseInfoCollection", [])

                # Find the specific warehouse
                for wh in warehouse_info:
                    if wh.get("WarehouseCode") == warehouse_code:
                        return {
                            "ok": True,
                            "data": {
                                "ItemCode": item_data.get("ItemCode"),
                                "ItemName": item_data.get("ItemName"),
                                "WarehouseCode": warehouse_code,
                                "InStock": wh.get("InStock", 0),
                                "Committed": wh.get("Committed", 0),
                                "Ordered": wh.get("Ordered", 0),
                                "Available": wh.get("InStock", 0) - wh.get("Committed", 0)
                            }
                        }

                return {"ok": False, "error": f"Warehouse {warehouse_code} not found for item {item_code}"}
            return result
        else:
            # Get stock for all warehouses
            url = f"{base_url}/Items('{quote(item_code, safe='')}')?$select=ItemCode,ItemName,QuantityOnStock,QuantityOrderedFromVendors,QuantityOrderedByCustomers,ItemWarehouseInfoCollection"
            result = _api_call(profile_name, url)

            if result.get("ok") and "result" in result:
                item_data = result["result"]
                warehouse_info = item_data.get("ItemWarehouseInfoCollection", [])

                warehouses = []
                for wh in warehouse_info:
                    if wh.get("InStock", 0) > 0 or wh.get("Committed", 0) > 0 or wh.get("Ordered", 0) > 0:
                        warehouses.append({
                            "WarehouseCode": wh.get("WarehouseCode"),
                            "WarehouseName": wh.get("WarehouseName"),
                            "InStock": wh.get("InStock", 0),
                            "Committed": wh.get("Committed", 0),
                            "Ordered": wh.get("Ordered", 0),
                            "Available": wh.get("InStock", 0) - wh.get("Committed", 0)
                        })

                return {
                    "ok": True,
                    "data": {
                        "ItemCode": item_data.get("ItemCode"),
                        "ItemName": item_data.get("ItemName"),
                        "TotalInStock": item_data.get("QuantityOnStock", 0),
                        "TotalOrderedFromVendors": item_data.get("QuantityOrderedFromVendors", 0),
                        "TotalOrderedByCustomers": item_data.get("QuantityOrderedByCustomers", 0),
                        "Warehouses": warehouses
                    }
                }
            return result

    except Exception as e:
        logger.exception("get_stock failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "login": login,
    "list_business_partners": list_business_partners,
    "get_business_partner": get_business_partner,
    "create_business_partner": create_business_partner,
    "list_orders": list_orders,
    "create_order": create_order,
    "list_items": list_items,
    "get_stock": get_stock,
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

    logger.info(f"Executing sap.{profile}.{action}")
    return ACTIONS[action](profile, params)
