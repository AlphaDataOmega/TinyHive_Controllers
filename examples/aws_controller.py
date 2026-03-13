"""AWS Controller — Amazon Web Services integration via REST APIs.

This controller provides integration with AWS services using Signature V4
authentication. It uses only Python standard library for all operations.

Method IDs:
  controller.aws.{profile}.list_buckets
  controller.aws.{profile}.upload_object
  controller.aws.{profile}.download_object
  controller.aws.{profile}.list_instances
  controller.aws.{profile}.invoke_lambda
  controller.aws.{profile}.send_sqs_message
  controller.aws.{profile}.publish_sns

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  {
    "region": "us-east-1",
    "access_key_env": "AWS_ACCESS_KEY_ID",
    "secret_key_env": "AWS_SECRET_ACCESS_KEY",
    "session_token_env": "AWS_SESSION_TOKEN"  // Optional, for temporary credentials
  }

Required IAM Permissions per Action:
  - list_buckets: s3:ListAllMyBuckets
  - upload_object: s3:PutObject
  - download_object: s3:GetObject
  - list_instances: ec2:DescribeInstances
  - invoke_lambda: lambda:InvokeFunction
  - send_sqs_message: sqs:SendMessage
  - publish_sns: sns:Publish

Dependencies:
  - None (Python standard library only)
"""

import base64
import hashlib
import hmac
import http.client
import json
import logging
import os
import ssl
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode, urlparse

logger = logging.getLogger("tinyhive.controller.aws")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

DEFAULT_TIMEOUT = 60


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with AWS configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available AWS profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


def _get_credentials(profile: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
    """Get AWS credentials from environment variables.

    Returns:
        Tuple of (access_key, secret_key, session_token)
        session_token may be None if not using temporary credentials.
    """
    access_key_env = profile.get("access_key_env", "AWS_ACCESS_KEY_ID")
    secret_key_env = profile.get("secret_key_env", "AWS_SECRET_ACCESS_KEY")
    session_token_env = profile.get("session_token_env", "AWS_SESSION_TOKEN")

    access_key = os.environ.get(access_key_env, "")
    secret_key = os.environ.get(secret_key_env, "")
    session_token = os.environ.get(session_token_env) if session_token_env else None

    if not access_key:
        raise ValueError(f"Environment variable '{access_key_env}' not set")
    if not secret_key:
        raise ValueError(f"Environment variable '{secret_key_env}' not set")

    return access_key, secret_key, session_token


# =============================================================================
# AWS Signature Version 4 Implementation
# =============================================================================

def _sign(key: bytes, msg: str) -> bytes:
    """Sign a message using HMAC-SHA256."""
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    """Derive the signing key for AWS Signature V4.

    The signing key is derived from the secret key through a series of HMAC operations:
    kDate = HMAC("AWS4" + secret_key, date_stamp)
    kRegion = HMAC(kDate, region)
    kService = HMAC(kRegion, service)
    kSigning = HMAC(kService, "aws4_request")
    """
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing


def _create_canonical_request(
    method: str,
    canonical_uri: str,
    canonical_querystring: str,
    canonical_headers: str,
    signed_headers: str,
    payload_hash: str
) -> str:
    """Create the canonical request for AWS Signature V4.

    CanonicalRequest =
      HTTPRequestMethod + '\n' +
      CanonicalURI + '\n' +
      CanonicalQueryString + '\n' +
      CanonicalHeaders + '\n' +
      SignedHeaders + '\n' +
      HexEncode(Hash(RequestPayload))
    """
    return "\n".join([
        method,
        canonical_uri,
        canonical_querystring,
        canonical_headers,
        signed_headers,
        payload_hash
    ])


def _create_string_to_sign(
    algorithm: str,
    amz_date: str,
    credential_scope: str,
    canonical_request: str
) -> str:
    """Create the string to sign for AWS Signature V4.

    StringToSign =
      Algorithm + '\n' +
      RequestDateTime + '\n' +
      CredentialScope + '\n' +
      HashedCanonicalRequest
    """
    canonical_request_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    return "\n".join([
        algorithm,
        amz_date,
        credential_scope,
        canonical_request_hash
    ])


def _sign_request_v4(
    method: str,
    host: str,
    uri: str,
    query_params: Dict[str, str],
    headers: Dict[str, str],
    payload: bytes,
    access_key: str,
    secret_key: str,
    session_token: Optional[str],
    region: str,
    service: str
) -> Dict[str, str]:
    """Generate AWS Signature V4 headers for a request.

    This implements the complete AWS Signature Version 4 signing process:
    1. Create canonical request
    2. Create string to sign
    3. Calculate signature
    4. Add signature to authorization header

    Returns:
        Dictionary of headers including the Authorization header.
    """
    algorithm = "AWS4-HMAC-SHA256"

    # Get current time in UTC
    t = datetime.now(timezone.utc)
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    # Create credential scope
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"

    # Hash the payload
    payload_hash = hashlib.sha256(payload).hexdigest()

    # Build headers to sign
    headers_to_sign = dict(headers)
    headers_to_sign["host"] = host
    headers_to_sign["x-amz-date"] = amz_date
    headers_to_sign["x-amz-content-sha256"] = payload_hash

    # Add session token if present (for temporary credentials)
    if session_token:
        headers_to_sign["x-amz-security-token"] = session_token

    # Create canonical headers (sorted, lowercase)
    sorted_headers = sorted(headers_to_sign.items(), key=lambda x: x[0].lower())
    canonical_headers = ""
    for key, value in sorted_headers:
        canonical_headers += f"{key.lower()}:{value.strip()}\n"

    # Create signed headers list
    signed_headers = ";".join(k.lower() for k, _ in sorted_headers)

    # Create canonical query string (sorted)
    if query_params:
        sorted_params = sorted(query_params.items())
        canonical_querystring = "&".join(
            f"{quote(k, safe='')}={quote(str(v), safe='')}"
            for k, v in sorted_params
        )
    else:
        canonical_querystring = ""

    # Ensure URI is properly encoded
    canonical_uri = uri if uri else "/"

    # Create canonical request
    canonical_request = _create_canonical_request(
        method,
        canonical_uri,
        canonical_querystring,
        canonical_headers,
        signed_headers,
        payload_hash
    )

    # Create string to sign
    string_to_sign = _create_string_to_sign(
        algorithm,
        amz_date,
        credential_scope,
        canonical_request
    )

    # Calculate signature
    signing_key = _get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    # Create authorization header
    authorization_header = (
        f"{algorithm} "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    # Return all headers needed for the request
    result_headers = {
        "Host": host,
        "X-Amz-Date": amz_date,
        "X-Amz-Content-Sha256": payload_hash,
        "Authorization": authorization_header,
    }

    if session_token:
        result_headers["X-Amz-Security-Token"] = session_token

    # Add any additional headers from the input
    for key, value in headers.items():
        if key.lower() not in ["host", "x-amz-date", "x-amz-content-sha256", "authorization"]:
            result_headers[key] = value

    return result_headers


# =============================================================================
# HTTP Helper using http.client
# =============================================================================

def _api_call(
    host: str,
    method: str,
    uri: str,
    query_params: Dict[str, str],
    headers: Dict[str, str],
    body: bytes,
    access_key: str,
    secret_key: str,
    session_token: Optional[str],
    region: str,
    service: str,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """Make an authenticated AWS API call using http.client.HTTPSConnection.

    This handles:
    - Signing the request with AWS Signature V4
    - Making the HTTPS request
    - Parsing the response

    Returns:
        Dictionary with "ok" status and either "result"/"data" or "error".
    """
    # Sign the request
    signed_headers = _sign_request_v4(
        method=method,
        host=host,
        uri=uri,
        query_params=query_params,
        headers=headers,
        payload=body,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        service=service
    )

    # Build the full path with query string
    if query_params:
        sorted_params = sorted(query_params.items())
        query_string = "&".join(
            f"{quote(k, safe='')}={quote(str(v), safe='')}"
            for k, v in sorted_params
        )
        full_path = f"{uri}?{query_string}"
    else:
        full_path = uri

    try:
        # Create HTTPS connection
        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection(host, timeout=timeout, context=context)

        # Make the request
        conn.request(method, full_path, body=body if body else None, headers=signed_headers)

        # Get response
        response = conn.getresponse()
        response_body = response.read()

        conn.close()

        if 200 <= response.status < 300:
            return {
                "ok": True,
                "result": response_body,
                "status_code": response.status,
                "headers": dict(response.getheaders())
            }
        else:
            error_text = response_body.decode("utf-8", errors="replace")
            logger.error("AWS API error %d: %s", response.status, error_text[:500])
            return {
                "ok": False,
                "error": f"HTTP {response.status}: {error_text[:500]}",
                "status_code": response.status
            }

    except http.client.HTTPException as e:
        logger.error("HTTP error: %s", str(e))
        return {"ok": False, "error": f"HTTP error: {str(e)}"}
    except ssl.SSLError as e:
        logger.error("SSL error: %s", str(e))
        return {"ok": False, "error": f"SSL error: {str(e)}"}
    except Exception as e:
        logger.exception("Unexpected error in AWS API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# XML Parsing Helpers
# =============================================================================

def _parse_xml_response(xml_bytes: bytes, namespace: str = "") -> ET.Element:
    """Parse XML response and return the root element."""
    return ET.fromstring(xml_bytes)


def _find_text(element: ET.Element, path: str, namespace: str = "", default: str = "") -> str:
    """Find text in XML element, handling namespaces."""
    if namespace:
        # Replace tag names with namespaced versions
        parts = path.split("/")
        ns_path = "/".join(f"{{{namespace}}}{p}" if p and not p.startswith("{") else p for p in parts)
        found = element.find(ns_path)
    else:
        found = element.find(path)
    return found.text if found is not None and found.text else default


def _find_all(element: ET.Element, path: str, namespace: str = "") -> List[ET.Element]:
    """Find all matching elements, handling namespaces."""
    if namespace:
        parts = path.split("/")
        ns_path = "/".join(f"{{{namespace}}}{p}" if p and not p.startswith("{") else p for p in parts)
        return element.findall(ns_path)
    return element.findall(path)


# =============================================================================
# S3 Actions
# =============================================================================

def list_buckets(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all S3 buckets owned by the authenticated user.

    Required IAM Permission: s3:ListAllMyBuckets

    Params:
        None required

    Returns:
        List of buckets with name and creation date.
    """
    profile = load_profile(profile_name)
    access_key, secret_key, session_token = _get_credentials(profile)
    region = profile.get("region", "us-east-1")

    # S3 list buckets endpoint
    host = "s3.amazonaws.com"

    result = _api_call(
        host=host,
        method="GET",
        uri="/",
        query_params={},
        headers={},
        body=b"",
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        service="s3"
    )

    if not result.get("ok"):
        return result

    # Parse XML response
    try:
        xml_data = result["result"]
        root = _parse_xml_response(xml_data)

        # S3 namespace
        ns = "http://s3.amazonaws.com/doc/2006-03-01/"

        buckets = []
        buckets_element = root.find(f"{{{ns}}}Buckets")
        if buckets_element is not None:
            for bucket in buckets_element.findall(f"{{{ns}}}Bucket"):
                name = bucket.find(f"{{{ns}}}Name")
                creation_date = bucket.find(f"{{{ns}}}CreationDate")
                buckets.append({
                    "name": name.text if name is not None else "",
                    "creation_date": creation_date.text if creation_date is not None else ""
                })

        return {"ok": True, "result": {"buckets": buckets, "count": len(buckets)}}

    except ET.ParseError as e:
        return {"ok": False, "error": f"Failed to parse XML response: {str(e)}"}


def upload_object(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload an object to S3.

    Required IAM Permission: s3:PutObject

    Params:
        bucket (str): Target S3 bucket name (required)
        key (str): Object key/path in the bucket (required)
        data (str): Content to upload as string
        data_base64 (str): Content to upload as base64-encoded bytes
        local_path (str): Path to local file to upload
        content_type (str): MIME type (default: application/octet-stream)

    Note: Provide one of data, data_base64, or local_path.
    """
    profile = load_profile(profile_name)
    access_key, secret_key, session_token = _get_credentials(profile)
    region = profile.get("region", "us-east-1")

    bucket = params.get("bucket", "")
    key = params.get("key", "")
    content_type = params.get("content_type", "application/octet-stream")

    if not bucket:
        return {"ok": False, "error": "bucket is required"}
    if not key:
        return {"ok": False, "error": "key is required"}

    # Get the data to upload
    if "data" in params:
        body = params["data"].encode("utf-8")
    elif "data_base64" in params:
        body = base64.b64decode(params["data_base64"])
    elif "local_path" in params:
        local_path = Path(params["local_path"]).expanduser()
        if not local_path.exists():
            return {"ok": False, "error": f"File not found: {params['local_path']}"}
        body = local_path.read_bytes()
    else:
        return {"ok": False, "error": "One of data, data_base64, or local_path is required"}

    # S3 PUT object endpoint (virtual-hosted style)
    host = f"{bucket}.s3.{region}.amazonaws.com"
    uri = f"/{quote(key, safe='/')}"

    headers = {
        "Content-Type": content_type,
        "Content-Length": str(len(body))
    }

    result = _api_call(
        host=host,
        method="PUT",
        uri=uri,
        query_params={},
        headers=headers,
        body=body,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        service="s3"
    )

    if not result.get("ok"):
        return result

    # Extract ETag from response headers
    response_headers = result.get("headers", {})
    etag = response_headers.get("ETag", response_headers.get("etag", "")).strip('"')

    return {
        "ok": True,
        "result": {
            "bucket": bucket,
            "key": key,
            "size": len(body),
            "etag": etag
        }
    }


def download_object(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Download an object from S3.

    Required IAM Permission: s3:GetObject

    Params:
        bucket (str): Source S3 bucket name (required)
        key (str): Object key/path in the bucket (required)
        local_path (str): Path to save file locally (optional)

    Returns:
        If local_path provided: path and size info
        Otherwise: content (utf-8 or base64 encoded) and metadata
    """
    profile = load_profile(profile_name)
    access_key, secret_key, session_token = _get_credentials(profile)
    region = profile.get("region", "us-east-1")

    bucket = params.get("bucket", "")
    key = params.get("key", "")
    local_path = params.get("local_path")

    if not bucket:
        return {"ok": False, "error": "bucket is required"}
    if not key:
        return {"ok": False, "error": "key is required"}

    # S3 GET object endpoint (virtual-hosted style)
    host = f"{bucket}.s3.{region}.amazonaws.com"
    uri = f"/{quote(key, safe='/')}"

    result = _api_call(
        host=host,
        method="GET",
        uri=uri,
        query_params={},
        headers={},
        body=b"",
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        service="s3"
    )

    if not result.get("ok"):
        return result

    content = result["result"]
    response_headers = result.get("headers", {})

    if local_path:
        # Save to file
        path = Path(local_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {
            "ok": True,
            "result": {
                "path": str(path),
                "size": len(content),
                "content_type": response_headers.get("Content-Type", "")
            }
        }
    else:
        # Return content directly
        try:
            decoded = content.decode("utf-8")
            return {
                "ok": True,
                "result": {
                    "data": decoded,
                    "encoding": "utf-8",
                    "size": len(content),
                    "content_type": response_headers.get("Content-Type", "")
                }
            }
        except UnicodeDecodeError:
            return {
                "ok": True,
                "result": {
                    "data": base64.b64encode(content).decode("ascii"),
                    "encoding": "base64",
                    "size": len(content),
                    "content_type": response_headers.get("Content-Type", "")
                }
            }


# =============================================================================
# EC2 Actions
# =============================================================================

def list_instances(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List EC2 instances with optional filters.

    Required IAM Permission: ec2:DescribeInstances

    Params:
        filters (dict): Optional filters as key-value pairs
            Example: {"instance-state-name": "running", "tag:Environment": "prod"}
        instance_ids (list): Optional list of specific instance IDs to describe
        max_results (int): Maximum number of results (default: 100)

    Returns:
        List of instances with id, type, state, IPs, and tags.
    """
    profile = load_profile(profile_name)
    access_key, secret_key, session_token = _get_credentials(profile)
    region = profile.get("region", "us-east-1")

    # EC2 endpoint
    host = f"ec2.{region}.amazonaws.com"

    # Build query parameters for DescribeInstances
    query_params = {
        "Action": "DescribeInstances",
        "Version": "2016-11-15"
    }

    # Add filters if provided
    filters = params.get("filters", {})
    filter_idx = 1
    for key, value in filters.items():
        query_params[f"Filter.{filter_idx}.Name"] = key
        if isinstance(value, list):
            for i, v in enumerate(value, 1):
                query_params[f"Filter.{filter_idx}.Value.{i}"] = v
        else:
            query_params[f"Filter.{filter_idx}.Value.1"] = value
        filter_idx += 1

    # Add instance IDs if provided
    instance_ids = params.get("instance_ids", [])
    for i, instance_id in enumerate(instance_ids, 1):
        query_params[f"InstanceId.{i}"] = instance_id

    # Add max results
    max_results = params.get("max_results", 100)
    query_params["MaxResults"] = str(max_results)

    result = _api_call(
        host=host,
        method="GET",
        uri="/",
        query_params=query_params,
        headers={},
        body=b"",
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        service="ec2"
    )

    if not result.get("ok"):
        return result

    # Parse XML response
    try:
        xml_data = result["result"]
        root = _parse_xml_response(xml_data)

        # EC2 namespace
        ns = "http://ec2.amazonaws.com/doc/2016-11-15/"

        instances = []

        # Find all reservations
        for reservation in root.findall(f".//{{{ns}}}reservationSet/{{{ns}}}item"):
            # Find all instances in this reservation
            for instance in reservation.findall(f".//{{{ns}}}instancesSet/{{{ns}}}item"):
                instance_data = {
                    "instance_id": "",
                    "instance_type": "",
                    "state": "",
                    "private_ip": "",
                    "public_ip": "",
                    "availability_zone": "",
                    "launch_time": "",
                    "tags": {}
                }

                # Extract instance ID
                instance_id_elem = instance.find(f"{{{ns}}}instanceId")
                if instance_id_elem is not None:
                    instance_data["instance_id"] = instance_id_elem.text or ""

                # Extract instance type
                instance_type_elem = instance.find(f"{{{ns}}}instanceType")
                if instance_type_elem is not None:
                    instance_data["instance_type"] = instance_type_elem.text or ""

                # Extract state
                state_elem = instance.find(f"{{{ns}}}instanceState/{{{ns}}}name")
                if state_elem is not None:
                    instance_data["state"] = state_elem.text or ""

                # Extract private IP
                private_ip_elem = instance.find(f"{{{ns}}}privateIpAddress")
                if private_ip_elem is not None:
                    instance_data["private_ip"] = private_ip_elem.text or ""

                # Extract public IP
                public_ip_elem = instance.find(f"{{{ns}}}ipAddress")
                if public_ip_elem is not None:
                    instance_data["public_ip"] = public_ip_elem.text or ""

                # Extract availability zone
                az_elem = instance.find(f"{{{ns}}}placement/{{{ns}}}availabilityZone")
                if az_elem is not None:
                    instance_data["availability_zone"] = az_elem.text or ""

                # Extract launch time
                launch_time_elem = instance.find(f"{{{ns}}}launchTime")
                if launch_time_elem is not None:
                    instance_data["launch_time"] = launch_time_elem.text or ""

                # Extract tags
                for tag in instance.findall(f"{{{ns}}}tagSet/{{{ns}}}item"):
                    key_elem = tag.find(f"{{{ns}}}key")
                    value_elem = tag.find(f"{{{ns}}}value")
                    if key_elem is not None and key_elem.text:
                        instance_data["tags"][key_elem.text] = value_elem.text if value_elem is not None else ""

                instances.append(instance_data)

        return {"ok": True, "result": {"instances": instances, "count": len(instances)}}

    except ET.ParseError as e:
        return {"ok": False, "error": f"Failed to parse XML response: {str(e)}"}


# =============================================================================
# Lambda Actions
# =============================================================================

def invoke_lambda(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Invoke an AWS Lambda function.

    Required IAM Permission: lambda:InvokeFunction

    Params:
        function_name (str): Function name, ARN, or partial ARN (required)
        payload (dict/str): JSON payload to send to the function (optional)
        invocation_type (str): "RequestResponse" (sync), "Event" (async),
                              or "DryRun" (validate only). Default: RequestResponse
        log_type (str): "Tail" to include execution log (up to 4KB). Default: None
        qualifier (str): Version or alias to invoke. Default: $LATEST

    Returns:
        Function response payload and execution metadata.
    """
    profile = load_profile(profile_name)
    access_key, secret_key, session_token = _get_credentials(profile)
    region = profile.get("region", "us-east-1")

    function_name = params.get("function_name", "")
    payload = params.get("payload", {})
    invocation_type = params.get("invocation_type", "RequestResponse")
    log_type = params.get("log_type")
    qualifier = params.get("qualifier")

    if not function_name:
        return {"ok": False, "error": "function_name is required"}

    # Lambda endpoint
    host = f"lambda.{region}.amazonaws.com"

    # Build URI
    encoded_name = quote(function_name, safe="")
    uri = f"/2015-03-31/functions/{encoded_name}/invocations"

    # Build query params
    query_params = {}
    if qualifier:
        query_params["Qualifier"] = qualifier

    # Build headers
    headers = {
        "X-Amz-Invocation-Type": invocation_type,
        "Content-Type": "application/json"
    }
    if log_type:
        headers["X-Amz-Log-Type"] = log_type

    # Serialize payload
    if isinstance(payload, (dict, list)):
        body = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, str):
        body = payload.encode("utf-8")
    else:
        body = b""

    result = _api_call(
        host=host,
        method="POST",
        uri=uri,
        query_params=query_params,
        headers=headers,
        body=body,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        service="lambda"
    )

    if not result.get("ok"):
        return result

    response_body = result["result"]
    response_headers = result.get("headers", {})

    # Parse response
    try:
        response_payload = json.loads(response_body.decode("utf-8")) if response_body else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        response_payload = response_body.decode("utf-8", errors="replace") if response_body else None

    response_data = {
        "payload": response_payload,
        "status_code": result.get("status_code"),
        "function_error": response_headers.get("X-Amz-Function-Error", response_headers.get("x-amz-function-error")),
        "executed_version": response_headers.get("X-Amz-Executed-Version", response_headers.get("x-amz-executed-version"))
    }

    # Include log result if requested
    log_result = response_headers.get("X-Amz-Log-Result", response_headers.get("x-amz-log-result"))
    if log_result:
        try:
            response_data["log_result"] = base64.b64decode(log_result).decode("utf-8")
        except Exception:
            response_data["log_result"] = log_result

    return {"ok": True, "result": response_data}


# =============================================================================
# SQS Actions
# =============================================================================

def send_sqs_message(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a message to an SQS queue.

    Required IAM Permission: sqs:SendMessage

    Params:
        queue_url (str): Full URL of the SQS queue (required)
        message_body (str): Message content (required)
        delay_seconds (int): Delay before message becomes visible (0-900). Default: 0
        message_attributes (dict): Custom message attributes (optional)
            Format: {"AttrName": {"DataType": "String", "StringValue": "value"}}
        message_group_id (str): Required for FIFO queues
        message_deduplication_id (str): Required for FIFO queues without content-based dedup

    Returns:
        Message ID and MD5 of message body.
    """
    profile = load_profile(profile_name)
    access_key, secret_key, session_token = _get_credentials(profile)
    region = profile.get("region", "us-east-1")

    queue_url = params.get("queue_url", "")
    message_body = params.get("message_body", "")
    delay_seconds = params.get("delay_seconds", 0)
    message_attributes = params.get("message_attributes", {})
    message_group_id = params.get("message_group_id")
    message_deduplication_id = params.get("message_deduplication_id")

    if not queue_url:
        return {"ok": False, "error": "queue_url is required"}
    if not message_body:
        return {"ok": False, "error": "message_body is required"}

    # Parse queue URL to get host
    parsed_url = urlparse(queue_url)
    host = parsed_url.netloc
    uri = parsed_url.path

    # Build query parameters for SendMessage action
    query_params = {
        "Action": "SendMessage",
        "Version": "2012-11-05",
        "MessageBody": message_body
    }

    if delay_seconds > 0:
        query_params["DelaySeconds"] = str(delay_seconds)

    if message_group_id:
        query_params["MessageGroupId"] = message_group_id

    if message_deduplication_id:
        query_params["MessageDeduplicationId"] = message_deduplication_id

    # Add message attributes
    attr_idx = 1
    for name, attr in message_attributes.items():
        query_params[f"MessageAttribute.{attr_idx}.Name"] = name
        query_params[f"MessageAttribute.{attr_idx}.Value.DataType"] = attr.get("DataType", "String")
        if "StringValue" in attr:
            query_params[f"MessageAttribute.{attr_idx}.Value.StringValue"] = attr["StringValue"]
        if "BinaryValue" in attr:
            query_params[f"MessageAttribute.{attr_idx}.Value.BinaryValue"] = attr["BinaryValue"]
        attr_idx += 1

    result = _api_call(
        host=host,
        method="POST",
        uri=uri,
        query_params=query_params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=b"",
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        service="sqs"
    )

    if not result.get("ok"):
        return result

    # Parse XML response
    try:
        xml_data = result["result"]
        root = _parse_xml_response(xml_data)

        # SQS namespace
        ns = "http://queue.amazonaws.com/doc/2012-11-05/"

        # Find SendMessageResult
        send_result = root.find(f".//{{{ns}}}SendMessageResult")
        if send_result is None:
            # Try without namespace
            send_result = root.find(".//SendMessageResult")

        message_id = ""
        md5_body = ""

        if send_result is not None:
            msg_id_elem = send_result.find(f"{{{ns}}}MessageId")
            if msg_id_elem is None:
                msg_id_elem = send_result.find("MessageId")
            if msg_id_elem is not None:
                message_id = msg_id_elem.text or ""

            md5_elem = send_result.find(f"{{{ns}}}MD5OfMessageBody")
            if md5_elem is None:
                md5_elem = send_result.find("MD5OfMessageBody")
            if md5_elem is not None:
                md5_body = md5_elem.text or ""

        return {
            "ok": True,
            "result": {
                "message_id": message_id,
                "md5_of_message_body": md5_body
            }
        }

    except ET.ParseError as e:
        return {"ok": False, "error": f"Failed to parse XML response: {str(e)}"}


# =============================================================================
# SNS Actions
# =============================================================================

def publish_sns(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Publish a message to an SNS topic.

    Required IAM Permission: sns:Publish

    Params:
        topic_arn (str): ARN of the SNS topic (required, unless target_arn provided)
        target_arn (str): ARN of endpoint (for direct delivery, e.g., to mobile)
        phone_number (str): Phone number in E.164 format (for SMS)
        message (str): Message content (required)
        subject (str): Subject for email endpoints (optional)
        message_structure (str): Set to "json" for per-protocol messages
        message_attributes (dict): Custom message attributes (optional)
            Format: {"AttrName": {"DataType": "String", "StringValue": "value"}}

    Returns:
        Message ID.
    """
    profile = load_profile(profile_name)
    access_key, secret_key, session_token = _get_credentials(profile)
    region = profile.get("region", "us-east-1")

    topic_arn = params.get("topic_arn", "")
    target_arn = params.get("target_arn", "")
    phone_number = params.get("phone_number", "")
    message = params.get("message", "")
    subject = params.get("subject", "")
    message_structure = params.get("message_structure", "")
    message_attributes = params.get("message_attributes", {})

    if not message:
        return {"ok": False, "error": "message is required"}
    if not topic_arn and not target_arn and not phone_number:
        return {"ok": False, "error": "One of topic_arn, target_arn, or phone_number is required"}

    # SNS endpoint
    host = f"sns.{region}.amazonaws.com"

    # Build query parameters for Publish action
    query_params = {
        "Action": "Publish",
        "Version": "2010-03-31",
        "Message": message
    }

    if topic_arn:
        query_params["TopicArn"] = topic_arn
    if target_arn:
        query_params["TargetArn"] = target_arn
    if phone_number:
        query_params["PhoneNumber"] = phone_number
    if subject:
        query_params["Subject"] = subject
    if message_structure:
        query_params["MessageStructure"] = message_structure

    # Add message attributes
    attr_idx = 1
    for name, attr in message_attributes.items():
        query_params[f"MessageAttributes.entry.{attr_idx}.Name"] = name
        query_params[f"MessageAttributes.entry.{attr_idx}.Value.DataType"] = attr.get("DataType", "String")
        if "StringValue" in attr:
            query_params[f"MessageAttributes.entry.{attr_idx}.Value.StringValue"] = attr["StringValue"]
        if "BinaryValue" in attr:
            query_params[f"MessageAttributes.entry.{attr_idx}.Value.BinaryValue"] = attr["BinaryValue"]
        attr_idx += 1

    result = _api_call(
        host=host,
        method="POST",
        uri="/",
        query_params=query_params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=b"",
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        service="sns"
    )

    if not result.get("ok"):
        return result

    # Parse XML response
    try:
        xml_data = result["result"]
        root = _parse_xml_response(xml_data)

        # SNS namespace
        ns = "http://sns.amazonaws.com/doc/2010-03-31/"

        # Find PublishResult
        publish_result = root.find(f".//{{{ns}}}PublishResult")
        if publish_result is None:
            publish_result = root.find(".//PublishResult")

        message_id = ""

        if publish_result is not None:
            msg_id_elem = publish_result.find(f"{{{ns}}}MessageId")
            if msg_id_elem is None:
                msg_id_elem = publish_result.find("MessageId")
            if msg_id_elem is not None:
                message_id = msg_id_elem.text or ""

        return {"ok": True, "result": {"message_id": message_id}}

    except ET.ParseError as e:
        return {"ok": False, "error": f"Failed to parse XML response: {str(e)}"}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_buckets": list_buckets,
    "upload_object": upload_object,
    "download_object": download_object,
    "list_instances": list_instances,
    "invoke_lambda": invoke_lambda,
    "send_sqs_message": send_sqs_message,
    "publish_sns": publish_sns,
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
        logger.info(f"Executing aws.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
