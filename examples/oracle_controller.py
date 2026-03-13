"""Oracle Cloud Infrastructure (OCI) Controller for TinyHive.

This controller provides integration with Oracle Cloud Infrastructure services
using OCI request signatures (RSA-SHA256) for authentication.

Method IDs:
  controller.oracle.{profile}.list_instances
  controller.oracle.{profile}.get_instance
  controller.oracle.{profile}.start_instance
  controller.oracle.{profile}.stop_instance
  controller.oracle.{profile}.list_buckets
  controller.oracle.{profile}.list_objects
  controller.oracle.{profile}.list_databases
  controller.oracle.{profile}.list_compartments

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  {
    "tenancy_ocid": "ocid1.tenancy.oc1...",
    "user_ocid": "ocid1.user.oc1...",
    "fingerprint": "aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99",
    "private_key_path": "/path/to/oci_api_key.pem",
    "region": "us-ashburn-1",
    "compartment_ocid": "ocid1.compartment.oc1..."  // Default compartment
  }

Required IAM Policies per Action:
  - list_instances: Allow group X to read instance-family in compartment Y
  - get_instance: Allow group X to read instance-family in compartment Y
  - start_instance: Allow group X to use instance-family in compartment Y
  - stop_instance: Allow group X to use instance-family in compartment Y
  - list_buckets: Allow group X to read buckets in compartment Y
  - list_objects: Allow group X to read objects in compartment Y
  - list_databases: Allow group X to read autonomous-database-family in compartment Y
  - list_compartments: Allow group X to read compartments in tenancy

Dependencies:
  - cryptography (for RSA-SHA256 signing): pip install cryptography
"""

import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.oracle")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

# OCI API version dates
COMPUTE_API_VERSION = "20160918"
OBJECT_STORAGE_API_VERSION = "20160918"
DATABASE_API_VERSION = "20160918"
IDENTITY_API_VERSION = "20160918"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with OCI configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available OCI profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# OCI Request Signing (RSA-SHA256)
# =============================================================================

def _load_private_key(key_path: str) -> Any:
    """Load RSA private key from PEM file."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        raise ImportError(
            "cryptography library required for OCI request signing. "
            "Install with: pip install cryptography"
        )

    key_path = Path(key_path).expanduser()
    if not key_path.exists():
        alt_path = WORKSPACE / key_path
        if alt_path.exists():
            key_path = alt_path
        else:
            raise ValueError(f"Private key file not found: {key_path}")

    key_data = key_path.read_bytes()
    return serialization.load_pem_private_key(
        key_data,
        password=None,
        backend=default_backend()
    )


def _sign_request(
    private_key: Any,
    key_id: str,
    method: str,
    target: str,
    host: str,
    date: str,
    content_type: Optional[str] = None,
    content_length: Optional[int] = None,
    x_content_sha256: Optional[str] = None
) -> str:
    """
    Generate OCI request signature.

    OCI uses HTTP Signature (draft-cavage-http-signatures-08) with RSA-SHA256.
    """
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        raise ImportError(
            "cryptography library required for OCI request signing. "
            "Install with: pip install cryptography"
        )

    # Build signing string
    # For GET/DELETE/HEAD: (request-target) date host
    # For POST/PUT/PATCH: (request-target) date host content-type content-length x-content-sha256
    signing_parts = [
        f"(request-target): {method.lower()} {target}",
        f"date: {date}",
        f"host: {host}",
    ]
    headers_to_sign = "(request-target) date host"

    if method.upper() in ("POST", "PUT", "PATCH"):
        signing_parts.append(f"content-type: {content_type}")
        signing_parts.append(f"content-length: {content_length}")
        signing_parts.append(f"x-content-sha256: {x_content_sha256}")
        headers_to_sign = "(request-target) date host content-type content-length x-content-sha256"

    signing_string = "\n".join(signing_parts)

    # Sign with RSA-SHA256
    signature = private_key.sign(
        signing_string.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    signature_b64 = base64.b64encode(signature).decode("ascii")

    # Build Authorization header
    auth_header = (
        f'Signature version="1",'
        f'keyId="{key_id}",'
        f'algorithm="rsa-sha256",'
        f'headers="{headers_to_sign}",'
        f'signature="{signature_b64}"'
    )

    return auth_header


def _get_date_header() -> str:
    """Get RFC 7231 formatted date for HTTP Date header."""
    # Format: Thu, 05 Jan 2014 21:31:40 GMT
    now = datetime.now(timezone.utc)
    return now.strftime("%a, %d %b %Y %H:%M:%S GMT")


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    profile: Dict[str, Any],
    method: str,
    url: str,
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated OCI API call."""
    from urllib.parse import urlparse

    # Load private key
    private_key = _load_private_key(profile["private_key_path"])

    # Build key ID: {tenancy_ocid}/{user_ocid}/{fingerprint}
    key_id = f"{profile['tenancy_ocid']}/{profile['user_ocid']}/{profile['fingerprint']}"

    # Parse URL for signing
    parsed = urlparse(url)
    host = parsed.netloc
    target = parsed.path
    if parsed.query:
        target = f"{target}?{parsed.query}"

    # Get date
    date = _get_date_header()

    # Prepare headers
    headers = {
        "Date": date,
        "Host": host,
    }

    # For requests with body
    content_type = None
    content_length = None
    x_content_sha256 = None

    if method.upper() in ("POST", "PUT", "PATCH"):
        if data is None:
            data = b""
        content_type = "application/json"
        content_length = len(data)
        x_content_sha256 = base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")
        headers["Content-Type"] = content_type
        headers["Content-Length"] = str(content_length)
        headers["x-content-sha256"] = x_content_sha256

    # Sign request
    auth_header = _sign_request(
        private_key=private_key,
        key_id=key_id,
        method=method,
        target=target,
        host=host,
        date=date,
        content_type=content_type,
        content_length=content_length,
        x_content_sha256=x_content_sha256
    )
    headers["Authorization"] = auth_header

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
            error_code = error_data.get("code", "Unknown")
        except json.JSONDecodeError:
            error_message = error_body[:500]
            error_code = "Unknown"
        logger.error("OCI API error %d (%s): %s", e.code, error_code, error_message)
        return {"ok": False, "error": f"HTTP {e.code} ({error_code}): {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in OCI API call")
        return {"ok": False, "error": str(e)}


def _get_compute_url(region: str, path: str) -> str:
    """Build Compute API URL."""
    return f"https://iaas.{region}.oraclecloud.com/{COMPUTE_API_VERSION}{path}"


def _get_object_storage_url(region: str, path: str) -> str:
    """Build Object Storage API URL."""
    return f"https://objectstorage.{region}.oraclecloud.com/{OBJECT_STORAGE_API_VERSION}{path}"


def _get_database_url(region: str, path: str) -> str:
    """Build Database API URL."""
    return f"https://database.{region}.oraclecloud.com/{DATABASE_API_VERSION}{path}"


def _get_identity_url(region: str, path: str) -> str:
    """Build Identity API URL."""
    return f"https://identity.{region}.oraclecloud.com/{IDENTITY_API_VERSION}{path}"


# =============================================================================
# Compute Actions
# =============================================================================

def list_instances(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List compute instances in a compartment.

    Required IAM Policy: Allow group X to read instance-family in compartment Y

    Params:
        compartment_id (str): Compartment OCID (default: from profile)
        availability_domain (str): Filter by availability domain (optional)
        display_name (str): Filter by display name (optional)
        lifecycle_state (str): Filter by state: RUNNING, STOPPED, etc. (optional)
        limit (int): Maximum results to return (default: 100)
    """
    profile = load_profile(profile_name)
    region = profile.get("region", "us-ashburn-1")

    compartment_id = params.get("compartment_id", profile.get("compartment_ocid"))
    if not compartment_id:
        return {"ok": False, "error": "compartment_id required (in profile or params)"}

    query_params = {"compartmentId": compartment_id}

    if params.get("availability_domain"):
        query_params["availabilityDomain"] = params["availability_domain"]
    if params.get("display_name"):
        query_params["displayName"] = params["display_name"]
    if params.get("lifecycle_state"):
        query_params["lifecycleState"] = params["lifecycle_state"]
    if params.get("limit"):
        query_params["limit"] = params["limit"]

    url = _get_compute_url(region, f"/instances?{urlencode(query_params)}")
    result = _api_call(profile, "GET", url)

    if result.get("ok") and "data" in result:
        instances = result["data"] if isinstance(result["data"], list) else []
        return {
            "ok": True,
            "data": {
                "instances": [
                    {
                        "id": i.get("id"),
                        "display_name": i.get("displayName"),
                        "availability_domain": i.get("availabilityDomain"),
                        "shape": i.get("shape"),
                        "lifecycle_state": i.get("lifecycleState"),
                        "time_created": i.get("timeCreated"),
                        "region": i.get("region"),
                        "fault_domain": i.get("faultDomain"),
                        "image_id": i.get("imageId"),
                    }
                    for i in instances
                ]
            }
        }
    return result


def get_instance(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details of a specific compute instance.

    Required IAM Policy: Allow group X to read instance-family in compartment Y

    Params:
        instance_id (str): Instance OCID (required)
    """
    profile = load_profile(profile_name)
    region = profile.get("region", "us-ashburn-1")

    instance_id = params.get("instance_id")
    if not instance_id:
        return {"ok": False, "error": "instance_id required"}

    url = _get_compute_url(region, f"/instances/{quote(instance_id, safe='')}")
    result = _api_call(profile, "GET", url)

    if result.get("ok") and "data" in result:
        i = result["data"]
        return {
            "ok": True,
            "data": {
                "id": i.get("id"),
                "display_name": i.get("displayName"),
                "compartment_id": i.get("compartmentId"),
                "availability_domain": i.get("availabilityDomain"),
                "shape": i.get("shape"),
                "shape_config": i.get("shapeConfig"),
                "lifecycle_state": i.get("lifecycleState"),
                "time_created": i.get("timeCreated"),
                "region": i.get("region"),
                "fault_domain": i.get("faultDomain"),
                "image_id": i.get("imageId"),
                "source_details": i.get("sourceDetails"),
                "launch_options": i.get("launchOptions"),
                "metadata": i.get("metadata"),
                "extended_metadata": i.get("extendedMetadata"),
                "freeform_tags": i.get("freeformTags"),
                "defined_tags": i.get("definedTags"),
            }
        }
    return result


def start_instance(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Start a stopped compute instance.

    Required IAM Policy: Allow group X to use instance-family in compartment Y

    Params:
        instance_id (str): Instance OCID (required)
    """
    profile = load_profile(profile_name)
    region = profile.get("region", "us-ashburn-1")

    instance_id = params.get("instance_id")
    if not instance_id:
        return {"ok": False, "error": "instance_id required"}

    # OCI uses POST to instanceAction endpoint with action=START
    url = _get_compute_url(region, f"/instances/{quote(instance_id, safe='')}?action=START")
    result = _api_call(profile, "POST", url)

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "instance_id": instance_id,
                "action": "START",
                "status": "initiated"
            }
        }
    return result


def stop_instance(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stop a running compute instance.

    Required IAM Policy: Allow group X to use instance-family in compartment Y

    Params:
        instance_id (str): Instance OCID (required)
        force (bool): Force stop without graceful shutdown (default: false)
    """
    profile = load_profile(profile_name)
    region = profile.get("region", "us-ashburn-1")

    instance_id = params.get("instance_id")
    if not instance_id:
        return {"ok": False, "error": "instance_id required"}

    # OCI uses STOP for graceful, SOFTSTOP also available
    action = "STOP"
    if params.get("force"):
        action = "STOP"  # STOP is immediate, SOFTSTOP is graceful in OCI terminology

    url = _get_compute_url(region, f"/instances/{quote(instance_id, safe='')}?action={action}")
    result = _api_call(profile, "POST", url)

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "instance_id": instance_id,
                "action": action,
                "status": "initiated"
            }
        }
    return result


# =============================================================================
# Object Storage Actions
# =============================================================================

def list_buckets(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List Object Storage buckets in a compartment.

    Required IAM Policy: Allow group X to read buckets in compartment Y

    Params:
        namespace (str): Object Storage namespace (required)
        compartment_id (str): Compartment OCID (default: from profile)
        limit (int): Maximum results to return (default: 100)
    """
    profile = load_profile(profile_name)
    region = profile.get("region", "us-ashburn-1")

    namespace = params.get("namespace")
    if not namespace:
        return {"ok": False, "error": "namespace required"}

    compartment_id = params.get("compartment_id", profile.get("compartment_ocid"))
    if not compartment_id:
        return {"ok": False, "error": "compartment_id required (in profile or params)"}

    query_params = {"compartmentId": compartment_id}
    if params.get("limit"):
        query_params["limit"] = params["limit"]

    url = _get_object_storage_url(region, f"/n/{quote(namespace, safe='')}/b?{urlencode(query_params)}")
    result = _api_call(profile, "GET", url)

    if result.get("ok") and "data" in result:
        buckets = result["data"] if isinstance(result["data"], list) else []
        return {
            "ok": True,
            "data": {
                "buckets": [
                    {
                        "name": b.get("name"),
                        "namespace": b.get("namespace"),
                        "compartment_id": b.get("compartmentId"),
                        "created_by": b.get("createdBy"),
                        "time_created": b.get("timeCreated"),
                        "etag": b.get("etag"),
                        "freeform_tags": b.get("freeformTags"),
                        "defined_tags": b.get("definedTags"),
                    }
                    for b in buckets
                ]
            }
        }
    return result


def list_objects(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List objects in an Object Storage bucket.

    Required IAM Policy: Allow group X to read objects in compartment Y

    Params:
        namespace (str): Object Storage namespace (required)
        bucket_name (str): Bucket name (required)
        prefix (str): Filter objects by prefix (optional)
        delimiter (str): Delimiter for hierarchy (optional, e.g., '/')
        start (str): Start listing after this object name (optional)
        limit (int): Maximum results to return (default: 100)
        fields (str): Comma-separated list of fields to return (optional)
    """
    profile = load_profile(profile_name)
    region = profile.get("region", "us-ashburn-1")

    namespace = params.get("namespace")
    if not namespace:
        return {"ok": False, "error": "namespace required"}

    bucket_name = params.get("bucket_name")
    if not bucket_name:
        return {"ok": False, "error": "bucket_name required"}

    query_params = {}
    if params.get("prefix"):
        query_params["prefix"] = params["prefix"]
    if params.get("delimiter"):
        query_params["delimiter"] = params["delimiter"]
    if params.get("start"):
        query_params["start"] = params["start"]
    if params.get("limit"):
        query_params["limit"] = params["limit"]
    if params.get("fields"):
        query_params["fields"] = params["fields"]

    path = f"/n/{quote(namespace, safe='')}/b/{quote(bucket_name, safe='')}/o"
    if query_params:
        path = f"{path}?{urlencode(query_params)}"

    url = _get_object_storage_url(region, path)
    result = _api_call(profile, "GET", url)

    if result.get("ok") and "data" in result:
        data = result["data"]
        objects = data.get("objects", []) if isinstance(data, dict) else []
        prefixes = data.get("prefixes", []) if isinstance(data, dict) else []
        next_start = data.get("nextStartWith") if isinstance(data, dict) else None

        return {
            "ok": True,
            "data": {
                "objects": [
                    {
                        "name": obj.get("name"),
                        "size": obj.get("size"),
                        "md5": obj.get("md5"),
                        "time_created": obj.get("timeCreated"),
                        "time_modified": obj.get("timeModified"),
                        "etag": obj.get("etag"),
                        "storage_tier": obj.get("storageTier"),
                    }
                    for obj in objects
                ],
                "prefixes": prefixes,
                "next_start_with": next_start,
            }
        }
    return result


# =============================================================================
# Database Actions
# =============================================================================

def list_databases(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List Autonomous Databases in a compartment.

    Required IAM Policy: Allow group X to read autonomous-database-family in compartment Y

    Params:
        compartment_id (str): Compartment OCID (default: from profile)
        display_name (str): Filter by display name (optional)
        db_workload (str): Filter by workload type: OLTP, DW, AJD, APEX (optional)
        lifecycle_state (str): Filter by state: AVAILABLE, STOPPED, etc. (optional)
        limit (int): Maximum results to return (default: 100)
    """
    profile = load_profile(profile_name)
    region = profile.get("region", "us-ashburn-1")

    compartment_id = params.get("compartment_id", profile.get("compartment_ocid"))
    if not compartment_id:
        return {"ok": False, "error": "compartment_id required (in profile or params)"}

    query_params = {"compartmentId": compartment_id}

    if params.get("display_name"):
        query_params["displayName"] = params["display_name"]
    if params.get("db_workload"):
        query_params["dbWorkload"] = params["db_workload"]
    if params.get("lifecycle_state"):
        query_params["lifecycleState"] = params["lifecycle_state"]
    if params.get("limit"):
        query_params["limit"] = params["limit"]

    url = _get_database_url(region, f"/autonomousDatabases?{urlencode(query_params)}")
    result = _api_call(profile, "GET", url)

    if result.get("ok") and "data" in result:
        databases = result["data"] if isinstance(result["data"], list) else []
        return {
            "ok": True,
            "data": {
                "databases": [
                    {
                        "id": db.get("id"),
                        "display_name": db.get("displayName"),
                        "compartment_id": db.get("compartmentId"),
                        "db_name": db.get("dbName"),
                        "db_workload": db.get("dbWorkload"),
                        "db_version": db.get("dbVersion"),
                        "lifecycle_state": db.get("lifecycleState"),
                        "cpu_core_count": db.get("cpuCoreCount"),
                        "ocpu_count": db.get("ocpuCount"),
                        "data_storage_size_in_tbs": db.get("dataStorageSizeInTBs"),
                        "data_storage_size_in_gbs": db.get("dataStorageSizeInGBs"),
                        "is_free_tier": db.get("isFreeTier"),
                        "is_auto_scaling_enabled": db.get("isAutoScalingEnabled"),
                        "time_created": db.get("timeCreated"),
                        "connection_strings": db.get("connectionStrings"),
                        "service_console_url": db.get("serviceConsoleUrl"),
                        "freeform_tags": db.get("freeformTags"),
                        "defined_tags": db.get("definedTags"),
                    }
                    for db in databases
                ]
            }
        }
    return result


# =============================================================================
# Identity Actions
# =============================================================================

def list_compartments(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List compartments in the tenancy.

    Required IAM Policy: Allow group X to read compartments in tenancy

    Params:
        compartment_id (str): Parent compartment OCID (default: tenancy root)
        access_level (str): ACCESSIBLE or ANY (default: ACCESSIBLE)
        compartment_id_in_subtree (bool): Include all subcompartments (default: false)
        lifecycle_state (str): Filter by state: ACTIVE, DELETED, etc. (optional)
        limit (int): Maximum results to return (default: 100)
    """
    profile = load_profile(profile_name)
    region = profile.get("region", "us-ashburn-1")

    # Default to tenancy root if not specified
    compartment_id = params.get("compartment_id", profile.get("tenancy_ocid"))
    if not compartment_id:
        return {"ok": False, "error": "compartment_id required (in profile or params)"}

    query_params = {"compartmentId": compartment_id}

    if params.get("access_level"):
        query_params["accessLevel"] = params["access_level"]
    if params.get("compartment_id_in_subtree"):
        query_params["compartmentIdInSubtree"] = str(params["compartment_id_in_subtree"]).lower()
    if params.get("lifecycle_state"):
        query_params["lifecycleState"] = params["lifecycle_state"]
    if params.get("limit"):
        query_params["limit"] = params["limit"]

    url = _get_identity_url(region, f"/compartments?{urlencode(query_params)}")
    result = _api_call(profile, "GET", url)

    if result.get("ok") and "data" in result:
        compartments = result["data"] if isinstance(result["data"], list) else []
        return {
            "ok": True,
            "data": {
                "compartments": [
                    {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "description": c.get("description"),
                        "compartment_id": c.get("compartmentId"),
                        "lifecycle_state": c.get("lifecycleState"),
                        "time_created": c.get("timeCreated"),
                        "is_accessible": c.get("isAccessible"),
                        "freeform_tags": c.get("freeformTags"),
                        "defined_tags": c.get("definedTags"),
                    }
                    for c in compartments
                ]
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_instances": list_instances,
    "get_instance": get_instance,
    "start_instance": start_instance,
    "stop_instance": stop_instance,
    "list_buckets": list_buckets,
    "list_objects": list_objects,
    "list_databases": list_databases,
    "list_compartments": list_compartments,
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
        logger.info(f"Executing oracle.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
