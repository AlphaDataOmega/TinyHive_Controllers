"""GCP Controller — Google Cloud Platform integration via REST APIs.

This controller provides integration with Google Cloud Platform services
using OAuth2 service account authentication. It supports both service
account JSON key files and Application Default Credentials (ADC).

Method IDs:
  controller.gcp.{profile}.list_gcs_buckets
  controller.gcp.{profile}.upload_to_gcs
  controller.gcp.{profile}.download_from_gcs
  controller.gcp.{profile}.list_compute_instances
  controller.gcp.{profile}.invoke_cloud_function
  controller.gcp.{profile}.publish_pubsub

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  Option 1 - Service Account JSON:
    {
      "project_id": "my-gcp-project",
      "service_account_path": "/path/to/service-account.json",
      "default_region": "us-central1",
      "default_zone": "us-central1-a"
    }

  Option 2 - Application Default Credentials (ADC):
    {
      "project_id": "my-gcp-project",
      "use_adc": true,
      "token_env": "GOOGLE_ACCESS_TOKEN",
      "default_region": "us-central1",
      "default_zone": "us-central1-a"
    }

Required IAM Roles per Action:
  - list_gcs_buckets: roles/storage.viewer
  - upload_to_gcs: roles/storage.objectCreator
  - download_from_gcs: roles/storage.objectViewer
  - list_compute_instances: roles/compute.viewer
  - invoke_cloud_function: roles/cloudfunctions.invoker
  - publish_pubsub: roles/pubsub.publisher

Dependencies:
  - cryptography (for service account JWT signing): pip install cryptography
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode

logger = logging.getLogger("tinyhive.controller.gcp")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# GCP API endpoints
GCS_API_BASE = "https://storage.googleapis.com/storage/v1"
GCS_UPLOAD_BASE = "https://storage.googleapis.com/upload/storage/v1"
COMPUTE_API_BASE = "https://compute.googleapis.com/compute/v1"
CLOUDFUNCTIONS_API_BASE = "https://cloudfunctions.googleapis.com/v2"
PUBSUB_API_BASE = "https://pubsub.googleapis.com/v1"
OAUTH_TOKEN_URI = "https://oauth2.googleapis.com/token"

# Scopes required for GCP APIs
GCP_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/devstorage.full_control",
    "https://www.googleapis.com/auth/compute",
    "https://www.googleapis.com/auth/cloudfunctions",
    "https://www.googleapis.com/auth/pubsub",
]

# Token cache: profile_name -> (token, expiry_timestamp)
_token_cache: Dict[str, Tuple[str, float]] = {}

DEFAULT_TIMEOUT = 60
MAX_UPLOAD_SIZE = 5 * 1024 * 1024 * 1024  # 5GB


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with GCP configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available GCP profile names."""
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
    """Get OAuth2 access token for GCP API calls."""
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
        jwt = _create_jwt(service_account, GCP_SCOPES)
        token, expiry = _exchange_jwt_for_token(jwt)
        _token_cache[profile_name] = (token, expiry)
        return token

    if profile.get("use_adc"):
        env_var = profile.get("token_env", "GOOGLE_ACCESS_TOKEN")
        token = os.environ.get(env_var, "")
        if not token:
            raise ValueError(
                f"Environment variable '{env_var}' not set. "
                "Obtain a token with: gcloud auth print-access-token"
            )
        _token_cache[profile_name] = (token, time.time() + 1800)
        return token

    raise ValueError(
        "Profile must specify either 'service_account_path' or 'use_adc: true'."
    )


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
    """Make an authenticated GCP API call."""
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
        logger.error("GCP API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in GCP API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Cloud Storage (GCS) Actions
# =============================================================================

def list_gcs_buckets(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List Cloud Storage buckets in the project.

    Required IAM Role: roles/storage.viewer

    Params:
        project_id (str): GCP project ID (default: from profile)
        prefix (str): Filter buckets by name prefix (optional)
        max_results (int): Maximum buckets to return (default: 100)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    project_id = params.get("project_id", profile.get("project_id"))
    if not project_id:
        return {"ok": False, "error": "project_id required (in profile or params)"}

    query_params = {"project": project_id}
    if params.get("prefix"):
        query_params["prefix"] = params["prefix"]
    if params.get("max_results"):
        query_params["maxResults"] = params["max_results"]

    url = f"{GCS_API_BASE}/b?{urlencode(query_params)}"
    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        buckets = result["result"].get("items", [])
        return {
            "ok": True,
            "result": {
                "buckets": [
                    {
                        "name": b.get("name"),
                        "location": b.get("location"),
                        "storage_class": b.get("storageClass"),
                        "created": b.get("timeCreated"),
                    }
                    for b in buckets
                ]
            }
        }
    return result


def upload_to_gcs(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload a file or data to Cloud Storage.

    Required IAM Role: roles/storage.objectCreator

    Params:
        bucket (str): Target bucket name (required)
        object_name (str): Object name/path in bucket (required)
        local_path (str): Path to local file to upload
        data (str): Raw data to upload as string
        content_type (str): MIME type (default: application/octet-stream)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    bucket = params.get("bucket", "")
    object_name = params.get("object_name", "")
    local_path = params.get("local_path")
    data = params.get("data")
    content_type = params.get("content_type", "application/octet-stream")

    if not bucket:
        return {"ok": False, "error": "bucket required"}
    if not object_name:
        return {"ok": False, "error": "object_name required"}
    if not local_path and data is None:
        return {"ok": False, "error": "Either local_path or data required"}

    if local_path:
        path = Path(local_path).expanduser()
        if not path.exists():
            return {"ok": False, "error": f"File not found: {local_path}"}
        if path.stat().st_size > MAX_UPLOAD_SIZE:
            return {"ok": False, "error": f"File too large. Max size: {MAX_UPLOAD_SIZE} bytes"}
        upload_data = path.read_bytes()
    else:
        upload_data = data.encode("utf-8") if isinstance(data, str) else data

    encoded_object = quote(object_name, safe="")
    url = f"{GCS_UPLOAD_BASE}/b/{bucket}/o?uploadType=media&name={encoded_object}"

    result = _api_call(token, url, method="POST", data=upload_data, content_type=content_type)

    if result.get("ok") and "result" in result:
        obj = result["result"]
        return {
            "ok": True,
            "result": {
                "name": obj.get("name"),
                "bucket": obj.get("bucket"),
                "size": obj.get("size"),
                "md5": obj.get("md5Hash"),
            }
        }
    return result


def download_from_gcs(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Download an object from Cloud Storage.

    Required IAM Role: roles/storage.objectViewer

    Params:
        bucket (str): Source bucket name (required)
        object_name (str): Object name/path in bucket (required)
        local_path (str): Path to save file locally (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    bucket = params.get("bucket", "")
    object_name = params.get("object_name", "")
    local_path = params.get("local_path")

    if not bucket:
        return {"ok": False, "error": "bucket required"}
    if not object_name:
        return {"ok": False, "error": "object_name required"}

    encoded_object = quote(object_name, safe="")
    url = f"{GCS_API_BASE}/b/{bucket}/o/{encoded_object}?alt=media"

    headers = {"Authorization": f"Bearer {token}"}

    try:
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            data = response.read()

            if local_path:
                path = Path(local_path).expanduser()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                return {"ok": True, "result": {"path": str(path), "size": len(data)}}
            else:
                try:
                    decoded = data.decode("utf-8")
                    return {"ok": True, "result": {"data": decoded, "size": len(data), "encoding": "utf-8"}}
                except UnicodeDecodeError:
                    return {"ok": True, "result": {"data": base64.b64encode(data).decode("ascii"), "size": len(data), "encoding": "base64"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:500]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# =============================================================================
# Compute Engine Actions
# =============================================================================

def list_compute_instances(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List Compute Engine instances.

    Required IAM Role: roles/compute.viewer

    Params:
        project_id (str): GCP project ID (default: from profile)
        zone (str): Compute zone (default: from profile, or lists all zones)
        filter (str): Filter expression (optional)
        max_results (int): Maximum instances to return (default: 100)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    project_id = params.get("project_id", profile.get("project_id"))
    if not project_id:
        return {"ok": False, "error": "project_id required (in profile or params)"}

    zone = params.get("zone", profile.get("default_zone"))

    query_params = {}
    if params.get("filter"):
        query_params["filter"] = params["filter"]
    if params.get("max_results"):
        query_params["maxResults"] = params["max_results"]

    if zone:
        url = f"{COMPUTE_API_BASE}/projects/{project_id}/zones/{zone}/instances"
        if query_params:
            url += f"?{urlencode(query_params)}"

        result = _api_call(token, url)

        if result.get("ok") and "result" in result:
            instances = result["result"].get("items", [])
            return {"ok": True, "result": {"instances": [_format_instance(i) for i in instances]}}
        return result
    else:
        url = f"{COMPUTE_API_BASE}/projects/{project_id}/aggregated/instances"
        if query_params:
            url += f"?{urlencode(query_params)}"

        result = _api_call(token, url)

        if result.get("ok") and "result" in result:
            instances = []
            items = result["result"].get("items", {})
            for zone_data in items.values():
                zone_instances = zone_data.get("instances", [])
                instances.extend([_format_instance(i) for i in zone_instances])
            return {"ok": True, "result": {"instances": instances}}
        return result


def _format_instance(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Format a Compute Engine instance for response."""
    zone_url = instance.get("zone", "")
    zone = zone_url.split("/")[-1] if zone_url else ""

    machine_type_url = instance.get("machineType", "")
    machine_type = machine_type_url.split("/")[-1] if machine_type_url else ""

    internal_ip = None
    external_ip = None
    network_interfaces = instance.get("networkInterfaces", [])
    if network_interfaces:
        internal_ip = network_interfaces[0].get("networkIP")
        access_configs = network_interfaces[0].get("accessConfigs", [])
        if access_configs:
            external_ip = access_configs[0].get("natIP")

    return {
        "name": instance.get("name"),
        "id": instance.get("id"),
        "zone": zone,
        "machine_type": machine_type,
        "status": instance.get("status"),
        "internal_ip": internal_ip,
        "external_ip": external_ip,
        "created": instance.get("creationTimestamp"),
        "labels": instance.get("labels", {}),
    }


# =============================================================================
# Cloud Functions Actions
# =============================================================================

def invoke_cloud_function(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Invoke a Cloud Function (2nd gen / Cloud Run functions).

    Required IAM Role: roles/cloudfunctions.invoker

    Params:
        function_url (str): Full HTTPS URL of the function (required)
        method (str): HTTP method (default: POST)
        payload (dict/str): JSON payload to send (optional)
        headers (dict): Additional headers (optional)
        timeout (int): Request timeout in seconds (default: 60)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    function_url = params.get("function_url", "")
    method = params.get("method", "POST").upper()
    payload = params.get("payload")
    extra_headers = params.get("headers", {})
    timeout = params.get("timeout", DEFAULT_TIMEOUT)

    if not function_url:
        return {"ok": False, "error": "function_url required"}
    if not function_url.startswith("https://"):
        return {"ok": False, "error": "function_url must be an HTTPS URL"}

    data = None
    if payload is not None:
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = str(payload).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers)

    try:
        req = Request(function_url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")

            try:
                parsed_body = json.loads(response_body)
            except json.JSONDecodeError:
                parsed_body = response_body

            return {"ok": True, "result": {"status_code": response.getcode(), "body": parsed_body}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {error_body[:1000]}", "status_code": e.code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# =============================================================================
# Pub/Sub Actions
# =============================================================================

def publish_pubsub(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Publish a message to a Pub/Sub topic.

    Required IAM Role: roles/pubsub.publisher

    Params:
        project_id (str): GCP project ID (default: from profile)
        topic (str): Topic name or full resource name (required)
        message (str): Message data as string (required)
        attributes (dict): Message attributes (optional)
        ordering_key (str): Ordering key for ordered delivery (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile, profile_name)

    project_id = params.get("project_id", profile.get("project_id"))
    if not project_id:
        return {"ok": False, "error": "project_id required (in profile or params)"}

    topic = params.get("topic", "")
    message = params.get("message", "")
    attributes = params.get("attributes", {})
    ordering_key = params.get("ordering_key")

    if not topic:
        return {"ok": False, "error": "topic required"}
    if not message:
        return {"ok": False, "error": "message required"}

    if not topic.startswith("projects/"):
        topic = f"projects/{project_id}/topics/{topic}"

    encoded_data = base64.b64encode(message.encode("utf-8")).decode("ascii")

    pubsub_message: Dict[str, Any] = {"data": encoded_data}
    if attributes:
        pubsub_message["attributes"] = attributes
    if ordering_key:
        pubsub_message["orderingKey"] = ordering_key

    request_body = {"messages": [pubsub_message]}

    url = f"{PUBSUB_API_BASE}/{topic}:publish"

    result = _api_call(token, url, method="POST", data=json.dumps(request_body).encode("utf-8"))

    if result.get("ok") and "result" in result:
        message_ids = result["result"].get("messageIds", [])
        return {"ok": True, "result": {"message_id": message_ids[0] if message_ids else None, "message_ids": message_ids}}
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_gcs_buckets": list_gcs_buckets,
    "upload_to_gcs": upload_to_gcs,
    "download_from_gcs": download_from_gcs,
    "list_compute_instances": list_compute_instances,
    "invoke_cloud_function": invoke_cloud_function,
    "publish_pubsub": publish_pubsub,
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
        logger.info(f"Executing gcp.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
