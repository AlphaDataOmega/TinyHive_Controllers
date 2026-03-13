"""Firebase Controller — Firebase/Google Cloud integration via REST APIs.

This controller provides integration with Firebase services including
Firestore, Realtime Database, Cloud Messaging (FCM), and Authentication.

Method IDs:
  controller.firebase.{profile}.get_document
  controller.firebase.{profile}.set_document
  controller.firebase.{profile}.query_collection
  controller.firebase.{profile}.delete_document
  controller.firebase.{profile}.get_rtdb
  controller.firebase.{profile}.set_rtdb
  controller.firebase.{profile}.send_fcm
  controller.firebase.{profile}.list_users

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  Option 1 - Service Account JSON (recommended for server-side):
    {
      "project_id": "my-firebase-project",
      "service_account_path": "/path/to/service-account.json"
    }

  Option 2 - ID Token from environment (for client-side or testing):
    {
      "project_id": "my-firebase-project",
      "token_env": "FIREBASE_ID_TOKEN"
    }

Required IAM Roles / Permissions:
  - get_document, set_document, query_collection, delete_document:
      roles/datastore.user or Firebase Firestore rules
  - get_rtdb, set_rtdb:
      Firebase Realtime Database rules
  - send_fcm:
      roles/cloudmessaging.messages.create
  - list_users:
      roles/firebaseauth.admin

Dependencies:
  - cryptography (for service account JWT signing): pip install cryptography
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
from urllib.parse import quote, urlencode

logger = logging.getLogger("tinyhive.controller.firebase")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# Firebase API endpoints
FIRESTORE_API_BASE = "https://firestore.googleapis.com/v1"
RTDB_API_BASE = "https://{project_id}-default-rtdb.firebaseio.com"
FCM_API_BASE = "https://fcm.googleapis.com/v1"
IDENTITY_TOOLKIT_API = "https://identitytoolkit.googleapis.com/v1"

# OAuth token endpoint
OAUTH_TOKEN_URI = "https://oauth2.googleapis.com/token"

# Scopes required for Firebase APIs
FIREBASE_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/datastore",
    "https://www.googleapis.com/auth/firebase.database",
    "https://www.googleapis.com/auth/firebase.messaging",
    "https://www.googleapis.com/auth/identitytoolkit",
]

# Token cache: profile_name -> (token, expiry_timestamp)
_token_cache: Dict[str, Tuple[str, float]] = {}

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Firebase configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Firebase profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# JWT / OAuth2 Service Account Authentication
# =============================================================================

def _base64url_encode(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _create_jwt(service_account: Dict[str, Any], scopes: List[str]) -> str:
    """Create a signed JWT for service account authentication."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        raise ImportError(
            "cryptography library required for service account auth. "
            "Install with: pip install cryptography"
        )

    now = int(time.time())

    header = {
        "alg": "RS256",
        "typ": "JWT",
        "kid": service_account.get("private_key_id", "")
    }

    claims = {
        "iss": service_account["client_email"],
        "sub": service_account["client_email"],
        "aud": OAUTH_TOKEN_URI,
        "iat": now,
        "exp": now + 3600,
        "scope": " ".join(scopes)
    }

    header_b64 = _base64url_encode(json.dumps(header).encode("utf-8"))
    claims_b64 = _base64url_encode(json.dumps(claims).encode("utf-8"))
    signing_input = f"{header_b64}.{claims_b64}".encode("utf-8")

    private_key_pem = service_account["private_key"].encode("utf-8")
    private_key = serialization.load_pem_private_key(
        private_key_pem,
        password=None,
        backend=default_backend()
    )

    signature = private_key.sign(
        signing_input,
        padding.PKCS1v15(),
        hashes.SHA256()
    )

    signature_b64 = _base64url_encode(signature)
    return f"{header_b64}.{claims_b64}.{signature_b64}"


def _exchange_jwt_for_token(jwt: str) -> Tuple[str, float]:
    """Exchange a signed JWT for an OAuth2 access token."""
    data = urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt
    }).encode("utf-8")

    req = Request(
        OAUTH_TOKEN_URI,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )

    with urlopen(req, timeout=30) as response:
        token_data = json.loads(response.read().decode("utf-8"))

    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)
    expiry = time.time() + expires_in - 60

    return access_token, expiry


def _get_access_token(profile: Dict[str, Any], profile_name: str) -> str:
    """Get OAuth2 access token for Firebase API calls."""
    if profile_name in _token_cache:
        token, expiry = _token_cache[profile_name]
        if time.time() < expiry:
            return token

    sa_path = profile.get("service_account_path")
    if sa_path:
        sa_path = Path(sa_path).expanduser()
        if not sa_path.exists():
            alt_path = WORKSPACE / sa_path
            if alt_path.exists():
                sa_path = alt_path
            else:
                raise ValueError(f"Service account file not found: {sa_path}")

        service_account = json.loads(sa_path.read_text())
        jwt = _create_jwt(service_account, FIREBASE_SCOPES)
        token, expiry = _exchange_jwt_for_token(jwt)
        _token_cache[profile_name] = (token, expiry)
        return token

    env_var = profile.get("token_env", "FIREBASE_ID_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(
            f"Environment variable '{env_var}' not set. "
            "Provide a Firebase ID token or use service account authentication."
        )
    # Cache env token for 30 minutes (ID tokens typically expire in 1 hour)
    _token_cache[profile_name] = (token, time.time() + 1800)
    return token


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    content_type: str = "application/json",
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Make an authenticated Firebase API call."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }
    if extra_headers:
        headers.update(extra_headers)

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
            error_message = error_data.get("error", {}).get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Firebase API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Firebase API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Firestore Helpers
# =============================================================================

def _firestore_base_url(project_id: str) -> str:
    """Get Firestore base URL for a project."""
    return f"{FIRESTORE_API_BASE}/projects/{project_id}/databases/(default)/documents"


def _python_to_firestore_value(value: Any) -> Dict[str, Any]:
    """Convert a Python value to Firestore Value format."""
    if value is None:
        return {"nullValue": None}
    elif isinstance(value, bool):
        return {"booleanValue": value}
    elif isinstance(value, int):
        return {"integerValue": str(value)}
    elif isinstance(value, float):
        return {"doubleValue": value}
    elif isinstance(value, str):
        return {"stringValue": value}
    elif isinstance(value, bytes):
        return {"bytesValue": base64.b64encode(value).decode("ascii")}
    elif isinstance(value, list):
        return {"arrayValue": {"values": [_python_to_firestore_value(v) for v in value]}}
    elif isinstance(value, dict):
        return {"mapValue": {"fields": {k: _python_to_firestore_value(v) for k, v in value.items()}}}
    else:
        return {"stringValue": str(value)}


def _firestore_value_to_python(value: Dict[str, Any]) -> Any:
    """Convert a Firestore Value to Python value."""
    if "nullValue" in value:
        return None
    elif "booleanValue" in value:
        return value["booleanValue"]
    elif "integerValue" in value:
        return int(value["integerValue"])
    elif "doubleValue" in value:
        return value["doubleValue"]
    elif "stringValue" in value:
        return value["stringValue"]
    elif "bytesValue" in value:
        return base64.b64decode(value["bytesValue"])
    elif "timestampValue" in value:
        return value["timestampValue"]
    elif "geoPointValue" in value:
        return value["geoPointValue"]
    elif "referenceValue" in value:
        return value["referenceValue"]
    elif "arrayValue" in value:
        values = value["arrayValue"].get("values", [])
        return [_firestore_value_to_python(v) for v in values]
    elif "mapValue" in value:
        fields = value["mapValue"].get("fields", {})
        return {k: _firestore_value_to_python(v) for k, v in fields.items()}
    else:
        return None


def _parse_firestore_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a Firestore document response into Python dict."""
    name = doc.get("name", "")
    # Extract document ID from name path
    doc_id = name.split("/")[-1] if name else None

    fields = doc.get("fields", {})
    data = {k: _firestore_value_to_python(v) for k, v in fields.items()}

    return {
        "id": doc_id,
        "path": name,
        "data": data,
        "createTime": doc.get("createTime"),
        "updateTime": doc.get("updateTime"),
    }


# =============================================================================
# Firestore Actions
# =============================================================================

def get_document(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a Firestore document by ID.

    Params:
        collection (str): Collection name (required)
        document_id (str): Document ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    project_id = profile.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id required in profile"}

    collection = params.get("collection")
    document_id = params.get("document_id")

    if not collection:
        return {"ok": False, "error": "collection required"}
    if not document_id:
        return {"ok": False, "error": "document_id required"}

    base_url = _firestore_base_url(project_id)
    url = f"{base_url}/{quote(collection, safe='')}/{quote(document_id, safe='')}"

    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        doc = _parse_firestore_document(result["result"])
        return {"ok": True, "data": doc}
    return result


def set_document(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Set/create a Firestore document.

    Params:
        collection (str): Collection name (required)
        document_id (str): Document ID (required)
        data (dict): Document data (required)
        merge (bool): Merge with existing document (default: False)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    project_id = profile.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id required in profile"}

    collection = params.get("collection")
    document_id = params.get("document_id")
    data = params.get("data")
    merge = params.get("merge", False)

    if not collection:
        return {"ok": False, "error": "collection required"}
    if not document_id:
        return {"ok": False, "error": "document_id required"}
    if data is None:
        return {"ok": False, "error": "data required"}

    base_url = _firestore_base_url(project_id)
    url = f"{base_url}/{quote(collection, safe='')}?documentId={quote(document_id, safe='')}"

    # Convert Python dict to Firestore document format
    firestore_doc = {
        "fields": {k: _python_to_firestore_value(v) for k, v in data.items()}
    }

    # Use PATCH for merge, POST for create/overwrite
    if merge:
        url = f"{base_url}/{quote(collection, safe='')}/{quote(document_id, safe='')}"
        # Add updateMask for merge
        field_paths = list(data.keys())
        update_mask = "&".join([f"updateMask.fieldPaths={quote(f, safe='')}" for f in field_paths])
        url = f"{url}?{update_mask}"
        method = "PATCH"
    else:
        method = "POST"

    result = _api_call(
        token, url,
        method=method,
        data=json.dumps(firestore_doc).encode("utf-8")
    )

    if result.get("ok") and "result" in result:
        doc = _parse_firestore_document(result["result"])
        return {"ok": True, "data": doc}
    return result


def query_collection(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Query a Firestore collection.

    Params:
        collection (str): Collection name (required)
        where (list): List of filter conditions, each as [field, op, value]
                     Operators: EQUAL, NOT_EQUAL, LESS_THAN, LESS_THAN_OR_EQUAL,
                               GREATER_THAN, GREATER_THAN_OR_EQUAL, ARRAY_CONTAINS,
                               IN, ARRAY_CONTAINS_ANY, NOT_IN
        order_by (list): List of [field, direction] pairs (direction: ASCENDING or DESCENDING)
        limit (int): Maximum documents to return (default: 100)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    project_id = profile.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id required in profile"}

    collection = params.get("collection")
    where = params.get("where", [])
    order_by = params.get("order_by", [])
    limit = params.get("limit", 100)

    if not collection:
        return {"ok": False, "error": "collection required"}

    # Build structured query
    structured_query: Dict[str, Any] = {
        "from": [{"collectionId": collection}],
        "limit": limit
    }

    # Add filters
    if where:
        filters = []
        for condition in where:
            if len(condition) != 3:
                return {"ok": False, "error": f"Invalid where condition: {condition}. Expected [field, op, value]"}
            field, op, value = condition
            filters.append({
                "fieldFilter": {
                    "field": {"fieldPath": field},
                    "op": op.upper() if isinstance(op, str) else op,
                    "value": _python_to_firestore_value(value)
                }
            })

        if len(filters) == 1:
            structured_query["where"] = filters[0]
        else:
            structured_query["where"] = {
                "compositeFilter": {
                    "op": "AND",
                    "filters": filters
                }
            }

    # Add ordering
    if order_by:
        orders = []
        for order in order_by:
            if isinstance(order, str):
                orders.append({"field": {"fieldPath": order}, "direction": "ASCENDING"})
            elif len(order) == 2:
                field, direction = order
                orders.append({
                    "field": {"fieldPath": field},
                    "direction": direction.upper() if isinstance(direction, str) else direction
                })
        if orders:
            structured_query["orderBy"] = orders

    # Execute query
    url = f"{FIRESTORE_API_BASE}/projects/{project_id}/databases/(default)/documents:runQuery"
    request_body = {"structuredQuery": structured_query}

    result = _api_call(
        token, url,
        method="POST",
        data=json.dumps(request_body).encode("utf-8")
    )

    if result.get("ok") and "result" in result:
        documents = []
        results = result["result"]
        # Handle single result vs array
        if isinstance(results, dict):
            results = [results]

        for item in results:
            if "document" in item:
                documents.append(_parse_firestore_document(item["document"]))

        return {"ok": True, "data": {"documents": documents, "count": len(documents)}}
    return result


def delete_document(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a Firestore document.

    Params:
        collection (str): Collection name (required)
        document_id (str): Document ID (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    project_id = profile.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id required in profile"}

    collection = params.get("collection")
    document_id = params.get("document_id")

    if not collection:
        return {"ok": False, "error": "collection required"}
    if not document_id:
        return {"ok": False, "error": "document_id required"}

    base_url = _firestore_base_url(project_id)
    url = f"{base_url}/{quote(collection, safe='')}/{quote(document_id, safe='')}"

    result = _api_call(token, url, method="DELETE")

    if result.get("ok"):
        return {"ok": True, "result": {"deleted": f"{collection}/{document_id}"}}
    return result


# =============================================================================
# Realtime Database Actions
# =============================================================================

def get_rtdb(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get data from Firebase Realtime Database.

    Params:
        path (str): Database path (required, e.g., "users/123")
        shallow (bool): Return only keys at path (default: False)
        order_by (str): Order results by child key or value (optional)
        limit_to_first (int): Limit to first N results (optional)
        limit_to_last (int): Limit to last N results (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    project_id = profile.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id required in profile"}

    path = params.get("path", "")
    shallow = params.get("shallow", False)
    order_by = params.get("order_by")
    limit_to_first = params.get("limit_to_first")
    limit_to_last = params.get("limit_to_last")

    # Build RTDB URL
    rtdb_base = profile.get("rtdb_url") or RTDB_API_BASE.format(project_id=project_id)
    path = path.strip("/")
    url = f"{rtdb_base}/{path}.json"

    # Add query parameters
    query_params = {"auth": token}
    if shallow:
        query_params["shallow"] = "true"
    if order_by:
        query_params["orderBy"] = f'"{order_by}"'
    if limit_to_first:
        query_params["limitToFirst"] = str(limit_to_first)
    if limit_to_last:
        query_params["limitToLast"] = str(limit_to_last)

    url = f"{url}?{urlencode(query_params)}"

    # RTDB uses query param auth, not header
    headers = {"Content-Type": "application/json"}

    try:
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                data = json.loads(response_body)
                return {"ok": True, "data": data}
            return {"ok": True, "data": None}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def set_rtdb(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Set data in Firebase Realtime Database.

    Params:
        path (str): Database path (required, e.g., "users/123")
        data (any): Data to set (required)
        method (str): HTTP method - PUT (overwrite) or PATCH (merge) (default: PUT)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    project_id = profile.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id required in profile"}

    path = params.get("path", "")
    data = params.get("data")
    method = params.get("method", "PUT").upper()

    if data is None:
        return {"ok": False, "error": "data required"}
    if method not in ("PUT", "PATCH"):
        return {"ok": False, "error": "method must be PUT or PATCH"}

    # Build RTDB URL
    rtdb_base = profile.get("rtdb_url") or RTDB_API_BASE.format(project_id=project_id)
    path = path.strip("/")
    url = f"{rtdb_base}/{path}.json?auth={token}"

    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8")

    try:
        req = Request(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                result = json.loads(response_body)
                return {"ok": True, "result": result}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# =============================================================================
# Firebase Cloud Messaging Actions
# =============================================================================

def send_fcm(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a Firebase Cloud Messaging notification.

    Params:
        token (str): FCM registration token (required)
        title (str): Notification title (required)
        body (str): Notification body (required)
        data (dict): Custom data payload (optional)
        image (str): Image URL for notification (optional)
        android (dict): Android-specific options (optional)
        apns (dict): iOS-specific options (optional)
        webpush (dict): Web push-specific options (optional)
    """
    profile = load_profile(profile_name)
    access_token = _get_access_token(profile, profile_name)

    project_id = profile.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id required in profile"}

    fcm_token = params.get("token")
    title = params.get("title")
    body = params.get("body")
    data = params.get("data", {})
    image = params.get("image")
    android = params.get("android")
    apns = params.get("apns")
    webpush = params.get("webpush")

    if not fcm_token:
        return {"ok": False, "error": "token required"}
    if not title:
        return {"ok": False, "error": "title required"}
    if not body:
        return {"ok": False, "error": "body required"}

    # Build FCM message
    message: Dict[str, Any] = {
        "token": fcm_token,
        "notification": {
            "title": title,
            "body": body
        }
    }

    if image:
        message["notification"]["image"] = image

    if data:
        # FCM data values must be strings
        message["data"] = {k: str(v) for k, v in data.items()}

    if android:
        message["android"] = android
    if apns:
        message["apns"] = apns
    if webpush:
        message["webpush"] = webpush

    url = f"{FCM_API_BASE}/projects/{project_id}/messages:send"
    request_body = {"message": message}

    result = _api_call(
        access_token, url,
        method="POST",
        data=json.dumps(request_body).encode("utf-8")
    )

    if result.get("ok") and "result" in result:
        return {"ok": True, "result": {"message_name": result["result"].get("name")}}
    return result


# =============================================================================
# Firebase Auth Actions
# =============================================================================

def list_users(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List Firebase Authentication users.

    Params:
        max_results (int): Maximum users to return (default: 100, max: 1000)
        page_token (str): Token for pagination (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    project_id = profile.get("project_id")
    if not project_id:
        return {"ok": False, "error": "project_id required in profile"}

    max_results = params.get("max_results", 100)
    page_token = params.get("page_token")

    if max_results > 1000:
        max_results = 1000

    # Build request body
    request_body: Dict[str, Any] = {
        "maxResults": max_results
    }
    if page_token:
        request_body["nextPageToken"] = page_token

    url = f"{IDENTITY_TOOLKIT_API}/projects/{project_id}/accounts:batchGet"

    result = _api_call(
        token, url,
        method="POST",
        data=json.dumps(request_body).encode("utf-8")
    )

    if result.get("ok") and "result" in result:
        users = result["result"].get("users", [])
        next_page_token = result["result"].get("nextPageToken")

        # Format user data
        formatted_users = []
        for user in users:
            formatted_users.append({
                "uid": user.get("localId"),
                "email": user.get("email"),
                "email_verified": user.get("emailVerified", False),
                "display_name": user.get("displayName"),
                "photo_url": user.get("photoUrl"),
                "phone_number": user.get("phoneNumber"),
                "disabled": user.get("disabled", False),
                "created_at": user.get("createdAt"),
                "last_login_at": user.get("lastLoginAt"),
                "provider_ids": [p.get("providerId") for p in user.get("providerUserInfo", [])]
            })

        response: Dict[str, Any] = {
            "users": formatted_users,
            "count": len(formatted_users)
        }
        if next_page_token:
            response["next_page_token"] = next_page_token

        return {"ok": True, "data": response}
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "get_document": get_document,
    "set_document": set_document,
    "query_collection": query_collection,
    "delete_document": delete_document,
    "get_rtdb": get_rtdb,
    "set_rtdb": set_rtdb,
    "send_fcm": send_fcm,
    "list_users": list_users,
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
        logger.info(f"Executing firebase.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
