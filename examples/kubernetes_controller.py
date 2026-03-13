"""
Kubernetes Controller for TinyHive

A controller for interacting with Kubernetes clusters via the Kubernetes API.
Supports bearer token authentication and kubeconfig-based configuration.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Bearer token auth profile:
{
    "api_server": "https://kubernetes.example.com:6443",
    "token_env": "K8S_TOKEN",
    "ca_cert_path": "/path/to/ca.crt",
    "verify_ssl": true,
    "default_namespace": "default"
}

Kubeconfig profile:
{
    "kubeconfig_path": "~/.kube/config",
    "context": "my-cluster",
    "default_namespace": "default"
}

Method IDs:
  controller.kubernetes.{profile}.list_pods
  controller.kubernetes.{profile}.get_pod
  controller.kubernetes.{profile}.list_deployments
  controller.kubernetes.{profile}.scale_deployment
  controller.kubernetes.{profile}.list_services
  controller.kubernetes.{profile}.list_namespaces
  controller.kubernetes.{profile}.get_logs
  controller.kubernetes.{profile}.apply_manifest

Required RBAC Permissions per Action:
  - list_pods: pods (list, watch)
  - get_pod: pods (get)
  - list_deployments: deployments (list, watch)
  - scale_deployment: deployments (get, patch), deployments/scale (get, update)
  - list_services: services (list, watch)
  - list_namespaces: namespaces (list)
  - get_logs: pods/log (get)
  - apply_manifest: varies by resource type

Dependencies:
  - None (standard library only)
"""

import base64
import json
import logging
import os
import ssl
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote

logger = logging.getLogger("tinyhive.controller.kubernetes")

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
        raise ValueError(f"Unknown profile '{name}'. Create {path} with Kubernetes configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available Kubernetes profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# Kubeconfig Parsing
# =============================================================================

def _parse_kubeconfig(kubeconfig_path: str, context_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Parse kubeconfig file and extract connection details.

    Returns dict with: api_server, token or client_cert/client_key, ca_cert
    """
    path = Path(kubeconfig_path).expanduser()
    if not path.exists():
        raise ValueError(f"Kubeconfig not found: {kubeconfig_path}")

    # Simple YAML parsing for kubeconfig (avoiding PyYAML dependency)
    content = path.read_text()
    kubeconfig = _parse_simple_yaml(content)

    # Get context
    contexts = {c["name"]: c["context"] for c in kubeconfig.get("contexts", [])}
    if context_name:
        if context_name not in contexts:
            raise ValueError(f"Context '{context_name}' not found in kubeconfig")
        context = contexts[context_name]
    else:
        current_context = kubeconfig.get("current-context")
        if not current_context:
            raise ValueError("No current-context set in kubeconfig")
        context = contexts.get(current_context)
        if not context:
            raise ValueError(f"Current context '{current_context}' not found")

    # Get cluster
    clusters = {c["name"]: c["cluster"] for c in kubeconfig.get("clusters", [])}
    cluster_name = context.get("cluster")
    cluster = clusters.get(cluster_name, {})

    # Get user
    users = {u["name"]: u["user"] for u in kubeconfig.get("users", [])}
    user_name = context.get("user")
    user = users.get(user_name, {})

    result = {
        "api_server": cluster.get("server", ""),
        "namespace": context.get("namespace", "default"),
    }

    # CA certificate
    if "certificate-authority" in cluster:
        result["ca_cert_path"] = cluster["certificate-authority"]
    elif "certificate-authority-data" in cluster:
        result["ca_cert_data"] = cluster["certificate-authority-data"]

    # Authentication
    if "token" in user:
        result["token"] = user["token"]
    elif "client-certificate" in user and "client-key" in user:
        result["client_cert_path"] = user["client-certificate"]
        result["client_key_path"] = user["client-key"]
    elif "client-certificate-data" in user and "client-key-data" in user:
        result["client_cert_data"] = user["client-certificate-data"]
        result["client_key_data"] = user["client-key-data"]

    return result


def _parse_simple_yaml(content: str) -> Dict[str, Any]:
    """
    Simple YAML parser for kubeconfig files.
    Handles basic kubeconfig structure without full YAML support.
    """
    try:
        import yaml
        return yaml.safe_load(content)
    except ImportError:
        pass

    # Fallback: very basic YAML parsing for kubeconfig
    # This handles the common kubeconfig structure
    lines = content.split('\n')
    result: Dict[str, Any] = {}
    stack: List[tuple] = [(result, -1)]  # (current_dict, indent_level)
    current_list: Optional[List] = None
    current_list_key: Optional[str] = None
    list_indent: int = -1

    for line in lines:
        # Skip empty lines and comments
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        # Calculate indent
        indent = len(line) - len(line.lstrip())

        # Handle list items
        if stripped.startswith('- '):
            if current_list is not None and indent >= list_indent:
                item_content = stripped[2:].strip()
                if ':' in item_content:
                    # List item is a dict
                    item_dict: Dict[str, Any] = {}
                    key, _, value = item_content.partition(':')
                    key = key.strip()
                    value = value.strip()
                    if value:
                        item_dict[key] = _parse_yaml_value(value)
                    current_list.append(item_dict)
                    stack.append((item_dict, indent))
                else:
                    current_list.append(_parse_yaml_value(item_content))
                continue

        # Handle key: value pairs
        if ':' in stripped:
            # Pop stack until we find parent at lower indent
            while len(stack) > 1 and stack[-1][1] >= indent:
                stack.pop()

            key, _, value = stripped.partition(':')
            key = key.strip().strip('"').strip("'")
            value = value.strip()

            current_dict = stack[-1][0]

            if value:
                # Simple key: value
                current_dict[key] = _parse_yaml_value(value)
                current_list = None
            else:
                # Check if next line starts a list
                current_dict[key] = {}
                stack.append((current_dict[key], indent))
                # Check if this should be a list
                next_line_idx = lines.index(line) + 1 if line in lines else -1
                if next_line_idx > 0 and next_line_idx < len(lines):
                    next_stripped = lines[next_line_idx].strip()
                    if next_stripped.startswith('- '):
                        current_dict[key] = []
                        current_list = current_dict[key]
                        current_list_key = key
                        list_indent = len(lines[next_line_idx]) - len(lines[next_line_idx].lstrip())
                        stack[-1] = (current_dict, indent)

    return result


def _parse_yaml_value(value: str) -> Any:
    """Parse a YAML value string."""
    value = value.strip()

    # Handle quoted strings
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    # Handle booleans
    if value.lower() in ('true', 'yes'):
        return True
    if value.lower() in ('false', 'no'):
        return False

    # Handle null
    if value.lower() in ('null', '~', ''):
        return None

    # Handle numbers
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


# =============================================================================
# Authentication & SSL Context
# =============================================================================

def _get_auth_config(profile: Dict[str, Any], profile_name: str) -> Dict[str, Any]:
    """
    Get authentication configuration from profile.

    Returns dict with: api_server, token, ssl_context, namespace
    """
    # Check for kubeconfig-based auth
    if "kubeconfig_path" in profile:
        kube_config = _parse_kubeconfig(
            profile["kubeconfig_path"],
            profile.get("context")
        )
        api_server = kube_config["api_server"]
        token = kube_config.get("token")
        namespace = profile.get("default_namespace", kube_config.get("namespace", "default"))

        # Build SSL context
        ssl_context = _build_ssl_context(
            ca_cert_path=kube_config.get("ca_cert_path"),
            ca_cert_data=kube_config.get("ca_cert_data"),
            client_cert_path=kube_config.get("client_cert_path"),
            client_key_path=kube_config.get("client_key_path"),
            client_cert_data=kube_config.get("client_cert_data"),
            client_key_data=kube_config.get("client_key_data"),
            verify_ssl=profile.get("verify_ssl", True)
        )

        return {
            "api_server": api_server,
            "token": token,
            "ssl_context": ssl_context,
            "namespace": namespace
        }

    # Direct configuration
    api_server = profile.get("api_server")
    if not api_server:
        raise ValueError("Profile must specify either 'kubeconfig_path' or 'api_server'")

    # Get token from environment
    token = None
    token_env = profile.get("token_env")
    if token_env:
        token = os.environ.get(token_env)
        if not token:
            raise ValueError(f"Environment variable '{token_env}' not set")
    elif "token" in profile:
        token = profile["token"]

    # Build SSL context
    ssl_context = _build_ssl_context(
        ca_cert_path=profile.get("ca_cert_path"),
        verify_ssl=profile.get("verify_ssl", True)
    )

    namespace = profile.get("default_namespace", "default")

    return {
        "api_server": api_server,
        "token": token,
        "ssl_context": ssl_context,
        "namespace": namespace
    }


def _build_ssl_context(
    ca_cert_path: Optional[str] = None,
    ca_cert_data: Optional[str] = None,
    client_cert_path: Optional[str] = None,
    client_key_path: Optional[str] = None,
    client_cert_data: Optional[str] = None,
    client_key_data: Optional[str] = None,
    verify_ssl: bool = True
) -> ssl.SSLContext:
    """Build SSL context for Kubernetes API calls."""
    if not verify_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    ctx = ssl.create_default_context()

    # Load CA certificate
    if ca_cert_path:
        ca_path = Path(ca_cert_path).expanduser()
        if ca_path.exists():
            ctx.load_verify_locations(str(ca_path))
    elif ca_cert_data:
        # Write to temp file (ssl module requires file path)
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.crt', delete=False) as f:
            f.write(base64.b64decode(ca_cert_data).decode('utf-8'))
            ctx.load_verify_locations(f.name)

    # Load client certificate
    if client_cert_path and client_key_path:
        cert_path = Path(client_cert_path).expanduser()
        key_path = Path(client_key_path).expanduser()
        if cert_path.exists() and key_path.exists():
            ctx.load_cert_chain(str(cert_path), str(key_path))
    elif client_cert_data and client_key_data:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.crt', delete=False) as cert_f:
            cert_f.write(base64.b64decode(client_cert_data).decode('utf-8'))
            cert_path = cert_f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.key', delete=False) as key_f:
            key_f.write(base64.b64decode(client_key_data).decode('utf-8'))
            key_path = key_f.name
        ctx.load_cert_chain(cert_path, key_path)

    return ctx


# =============================================================================
# HTTP Helpers
# =============================================================================

def _api_call(
    auth_config: Dict[str, Any],
    path: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    content_type: str = "application/json",
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Make an authenticated Kubernetes API call."""
    api_server = auth_config["api_server"].rstrip("/")
    url = f"{api_server}{path}"

    headers = {
        "Accept": "application/json",
        "Content-Type": content_type,
    }

    # Add bearer token if available
    token = auth_config.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if extra_headers:
        headers.update(extra_headers)

    try:
        req = Request(url, data=data, headers=headers, method=method)
        ssl_context = auth_config.get("ssl_context")

        with urlopen(req, timeout=timeout, context=ssl_context) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                return {"ok": True, "data": json.loads(response_body)}
            return {"ok": True, "data": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("Kubernetes API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in Kubernetes API call")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Pod Actions
# =============================================================================

def list_pods(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List pods in a namespace.

    Params:
        namespace (str): Namespace to list pods from (default: from profile)
        label_selector (str): Label selector to filter pods (optional)
        field_selector (str): Field selector to filter pods (optional)
        limit (int): Maximum number of pods to return (optional)
    """
    profile = load_profile(profile_name)
    auth_config = _get_auth_config(profile, profile_name)

    namespace = params.get("namespace", auth_config["namespace"])

    query_params = {}
    if params.get("label_selector"):
        query_params["labelSelector"] = params["label_selector"]
    if params.get("field_selector"):
        query_params["fieldSelector"] = params["field_selector"]
    if params.get("limit"):
        query_params["limit"] = params["limit"]

    path = f"/api/v1/namespaces/{quote(namespace, safe='')}/pods"
    if query_params:
        path += f"?{urlencode(query_params)}"

    result = _api_call(auth_config, path)

    if result.get("ok") and "data" in result:
        items = result["data"].get("items", [])
        return {
            "ok": True,
            "data": {
                "pods": [_format_pod(pod) for pod in items],
                "count": len(items)
            }
        }
    return result


def get_pod(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a specific pod.

    Params:
        namespace (str): Namespace of the pod (default: from profile)
        name (str): Name of the pod (required)
    """
    profile = load_profile(profile_name)
    auth_config = _get_auth_config(profile, profile_name)

    namespace = params.get("namespace", auth_config["namespace"])
    name = params.get("name")

    if not name:
        return {"ok": False, "error": "name is required"}

    path = f"/api/v1/namespaces/{quote(namespace, safe='')}/pods/{quote(name, safe='')}"
    result = _api_call(auth_config, path)

    if result.get("ok") and "data" in result:
        return {"ok": True, "data": _format_pod(result["data"])}
    return result


def _format_pod(pod: Dict[str, Any]) -> Dict[str, Any]:
    """Format pod data for response."""
    metadata = pod.get("metadata", {})
    spec = pod.get("spec", {})
    status = pod.get("status", {})

    containers = []
    for container in spec.get("containers", []):
        container_status = None
        for cs in status.get("containerStatuses", []):
            if cs.get("name") == container.get("name"):
                container_status = cs
                break

        containers.append({
            "name": container.get("name"),
            "image": container.get("image"),
            "ready": container_status.get("ready", False) if container_status else False,
            "restart_count": container_status.get("restartCount", 0) if container_status else 0,
        })

    return {
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
        "uid": metadata.get("uid"),
        "labels": metadata.get("labels", {}),
        "annotations": metadata.get("annotations", {}),
        "phase": status.get("phase"),
        "pod_ip": status.get("podIP"),
        "host_ip": status.get("hostIP"),
        "node_name": spec.get("nodeName"),
        "containers": containers,
        "created": metadata.get("creationTimestamp"),
        "conditions": status.get("conditions", []),
    }


# =============================================================================
# Deployment Actions
# =============================================================================

def list_deployments(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List deployments in a namespace.

    Params:
        namespace (str): Namespace to list deployments from (default: from profile)
        label_selector (str): Label selector to filter deployments (optional)
        limit (int): Maximum number of deployments to return (optional)
    """
    profile = load_profile(profile_name)
    auth_config = _get_auth_config(profile, profile_name)

    namespace = params.get("namespace", auth_config["namespace"])

    query_params = {}
    if params.get("label_selector"):
        query_params["labelSelector"] = params["label_selector"]
    if params.get("limit"):
        query_params["limit"] = params["limit"]

    path = f"/apis/apps/v1/namespaces/{quote(namespace, safe='')}/deployments"
    if query_params:
        path += f"?{urlencode(query_params)}"

    result = _api_call(auth_config, path)

    if result.get("ok") and "data" in result:
        items = result["data"].get("items", [])
        return {
            "ok": True,
            "data": {
                "deployments": [_format_deployment(dep) for dep in items],
                "count": len(items)
            }
        }
    return result


def scale_deployment(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scale a deployment to a specified number of replicas.

    Params:
        namespace (str): Namespace of the deployment (default: from profile)
        name (str): Name of the deployment (required)
        replicas (int): Desired number of replicas (required)
    """
    profile = load_profile(profile_name)
    auth_config = _get_auth_config(profile, profile_name)

    namespace = params.get("namespace", auth_config["namespace"])
    name = params.get("name")
    replicas = params.get("replicas")

    if not name:
        return {"ok": False, "error": "name is required"}
    if replicas is None:
        return {"ok": False, "error": "replicas is required"}

    try:
        replicas = int(replicas)
        if replicas < 0:
            return {"ok": False, "error": "replicas must be non-negative"}
    except (ValueError, TypeError):
        return {"ok": False, "error": "replicas must be an integer"}

    # Use PATCH to update the deployment spec
    patch_data = {
        "spec": {
            "replicas": replicas
        }
    }

    path = f"/apis/apps/v1/namespaces/{quote(namespace, safe='')}/deployments/{quote(name, safe='')}"
    data = json.dumps(patch_data).encode("utf-8")

    result = _api_call(
        auth_config,
        path,
        method="PATCH",
        data=data,
        content_type="application/strategic-merge-patch+json"
    )

    if result.get("ok") and "data" in result:
        return {
            "ok": True,
            "data": {
                "name": name,
                "namespace": namespace,
                "replicas": replicas,
                "message": f"Deployment {name} scaled to {replicas} replicas"
            }
        }
    return result


def _format_deployment(deployment: Dict[str, Any]) -> Dict[str, Any]:
    """Format deployment data for response."""
    metadata = deployment.get("metadata", {})
    spec = deployment.get("spec", {})
    status = deployment.get("status", {})

    return {
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
        "uid": metadata.get("uid"),
        "labels": metadata.get("labels", {}),
        "replicas": spec.get("replicas", 0),
        "ready_replicas": status.get("readyReplicas", 0),
        "available_replicas": status.get("availableReplicas", 0),
        "updated_replicas": status.get("updatedReplicas", 0),
        "strategy": spec.get("strategy", {}).get("type"),
        "selector": spec.get("selector", {}).get("matchLabels", {}),
        "created": metadata.get("creationTimestamp"),
        "conditions": status.get("conditions", []),
    }


# =============================================================================
# Service Actions
# =============================================================================

def list_services(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List services in a namespace.

    Params:
        namespace (str): Namespace to list services from (default: from profile)
        label_selector (str): Label selector to filter services (optional)
        limit (int): Maximum number of services to return (optional)
    """
    profile = load_profile(profile_name)
    auth_config = _get_auth_config(profile, profile_name)

    namespace = params.get("namespace", auth_config["namespace"])

    query_params = {}
    if params.get("label_selector"):
        query_params["labelSelector"] = params["label_selector"]
    if params.get("limit"):
        query_params["limit"] = params["limit"]

    path = f"/api/v1/namespaces/{quote(namespace, safe='')}/services"
    if query_params:
        path += f"?{urlencode(query_params)}"

    result = _api_call(auth_config, path)

    if result.get("ok") and "data" in result:
        items = result["data"].get("items", [])
        return {
            "ok": True,
            "data": {
                "services": [_format_service(svc) for svc in items],
                "count": len(items)
            }
        }
    return result


def _format_service(service: Dict[str, Any]) -> Dict[str, Any]:
    """Format service data for response."""
    metadata = service.get("metadata", {})
    spec = service.get("spec", {})
    status = service.get("status", {})

    ports = []
    for port in spec.get("ports", []):
        ports.append({
            "name": port.get("name"),
            "port": port.get("port"),
            "target_port": port.get("targetPort"),
            "protocol": port.get("protocol", "TCP"),
            "node_port": port.get("nodePort"),
        })

    # Get external IPs / LoadBalancer ingress
    external_ips = spec.get("externalIPs", [])
    load_balancer = status.get("loadBalancer", {})
    ingress = load_balancer.get("ingress", [])
    for ing in ingress:
        if ing.get("ip"):
            external_ips.append(ing["ip"])
        if ing.get("hostname"):
            external_ips.append(ing["hostname"])

    return {
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
        "uid": metadata.get("uid"),
        "labels": metadata.get("labels", {}),
        "type": spec.get("type", "ClusterIP"),
        "cluster_ip": spec.get("clusterIP"),
        "external_ips": external_ips,
        "ports": ports,
        "selector": spec.get("selector", {}),
        "created": metadata.get("creationTimestamp"),
    }


# =============================================================================
# Namespace Actions
# =============================================================================

def list_namespaces(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all namespaces in the cluster.

    Params:
        label_selector (str): Label selector to filter namespaces (optional)
        limit (int): Maximum number of namespaces to return (optional)
    """
    profile = load_profile(profile_name)
    auth_config = _get_auth_config(profile, profile_name)

    query_params = {}
    if params.get("label_selector"):
        query_params["labelSelector"] = params["label_selector"]
    if params.get("limit"):
        query_params["limit"] = params["limit"]

    path = "/api/v1/namespaces"
    if query_params:
        path += f"?{urlencode(query_params)}"

    result = _api_call(auth_config, path)

    if result.get("ok") and "data" in result:
        items = result["data"].get("items", [])
        namespaces = []
        for ns in items:
            metadata = ns.get("metadata", {})
            status = ns.get("status", {})
            namespaces.append({
                "name": metadata.get("name"),
                "uid": metadata.get("uid"),
                "labels": metadata.get("labels", {}),
                "phase": status.get("phase"),
                "created": metadata.get("creationTimestamp"),
            })
        return {
            "ok": True,
            "data": {
                "namespaces": namespaces,
                "count": len(namespaces)
            }
        }
    return result


# =============================================================================
# Logs Actions
# =============================================================================

def get_logs(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get logs from a pod container.

    Params:
        namespace (str): Namespace of the pod (default: from profile)
        name (str): Name of the pod (required)
        container (str): Container name (optional, required if pod has multiple containers)
        tail_lines (int): Number of lines from the end of the logs (default: 100)
        since_seconds (int): Return logs newer than this many seconds (optional)
        previous (bool): Return logs from previously terminated container (default: false)
        timestamps (bool): Include timestamps in log output (default: false)
    """
    profile = load_profile(profile_name)
    auth_config = _get_auth_config(profile, profile_name)

    namespace = params.get("namespace", auth_config["namespace"])
    name = params.get("name")
    container = params.get("container")
    tail_lines = params.get("tail_lines", 100)
    since_seconds = params.get("since_seconds")
    previous = params.get("previous", False)
    timestamps = params.get("timestamps", False)

    if not name:
        return {"ok": False, "error": "name is required"}

    query_params = {}
    if container:
        query_params["container"] = container
    if tail_lines:
        query_params["tailLines"] = tail_lines
    if since_seconds:
        query_params["sinceSeconds"] = since_seconds
    if previous:
        query_params["previous"] = "true"
    if timestamps:
        query_params["timestamps"] = "true"

    path = f"/api/v1/namespaces/{quote(namespace, safe='')}/pods/{quote(name, safe='')}/log"
    if query_params:
        path += f"?{urlencode(query_params)}"

    # Logs are returned as plain text
    api_server = auth_config["api_server"].rstrip("/")
    url = f"{api_server}{path}"

    headers = {
        "Accept": "text/plain",
    }

    token = auth_config.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        req = Request(url, headers=headers, method="GET")
        ssl_context = auth_config.get("ssl_context")

        with urlopen(req, timeout=DEFAULT_TIMEOUT, context=ssl_context) as response:
            logs = response.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "data": {
                    "pod": name,
                    "namespace": namespace,
                    "container": container,
                    "logs": logs,
                    "line_count": len(logs.splitlines())
                }
            }
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# =============================================================================
# Manifest Actions
# =============================================================================

def apply_manifest(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply a Kubernetes resource manifest (create or update).

    Params:
        manifest (dict): Kubernetes resource manifest (required)
        namespace (str): Namespace for namespaced resources (default: from profile or manifest)
    """
    profile = load_profile(profile_name)
    auth_config = _get_auth_config(profile, profile_name)

    manifest = params.get("manifest")
    if not manifest:
        return {"ok": False, "error": "manifest is required"}

    if isinstance(manifest, str):
        try:
            manifest = json.loads(manifest)
        except json.JSONDecodeError:
            return {"ok": False, "error": "manifest must be a valid JSON object"}

    api_version = manifest.get("apiVersion")
    kind = manifest.get("kind")
    metadata = manifest.get("metadata", {})
    name = metadata.get("name")

    if not api_version or not kind:
        return {"ok": False, "error": "manifest must have apiVersion and kind"}
    if not name:
        return {"ok": False, "error": "manifest metadata must have name"}

    # Determine namespace
    manifest_ns = metadata.get("namespace")
    param_ns = params.get("namespace")
    namespace = param_ns or manifest_ns or auth_config["namespace"]

    # Build API path based on apiVersion and kind
    path = _build_resource_path(api_version, kind, namespace, name)
    if path is None:
        return {"ok": False, "error": f"Unsupported resource type: {api_version}/{kind}"}

    data = json.dumps(manifest).encode("utf-8")

    # Try to get existing resource first
    get_result = _api_call(auth_config, path)

    if get_result.get("ok"):
        # Resource exists, use PATCH to update
        result = _api_call(
            auth_config,
            path,
            method="PATCH",
            data=data,
            content_type="application/strategic-merge-patch+json"
        )
        action = "updated"
    else:
        # Resource doesn't exist, use POST to create
        # Remove name from path for creation
        create_path = path.rsplit("/", 1)[0]
        result = _api_call(
            auth_config,
            create_path,
            method="POST",
            data=data,
            content_type="application/json"
        )
        action = "created"

    if result.get("ok"):
        return {
            "ok": True,
            "data": {
                "action": action,
                "kind": kind,
                "name": name,
                "namespace": namespace if _is_namespaced(kind) else None,
                "api_version": api_version,
            }
        }
    return result


def _build_resource_path(api_version: str, kind: str, namespace: str, name: str) -> Optional[str]:
    """Build API path for a resource."""
    # Map kinds to their API paths
    # Core API resources (apiVersion: v1)
    core_resources = {
        "Pod": "pods",
        "Service": "services",
        "ConfigMap": "configmaps",
        "Secret": "secrets",
        "PersistentVolumeClaim": "persistentvolumeclaims",
        "ServiceAccount": "serviceaccounts",
        "Namespace": "namespaces",
        "Node": "nodes",
        "PersistentVolume": "persistentvolumes",
    }

    # Apps API resources (apiVersion: apps/v1)
    apps_resources = {
        "Deployment": "deployments",
        "StatefulSet": "statefulsets",
        "DaemonSet": "daemonsets",
        "ReplicaSet": "replicasets",
    }

    # Batch API resources (apiVersion: batch/v1)
    batch_resources = {
        "Job": "jobs",
        "CronJob": "cronjobs",
    }

    # Networking resources (apiVersion: networking.k8s.io/v1)
    networking_resources = {
        "Ingress": "ingresses",
        "NetworkPolicy": "networkpolicies",
    }

    # RBAC resources (apiVersion: rbac.authorization.k8s.io/v1)
    rbac_resources = {
        "Role": "roles",
        "RoleBinding": "rolebindings",
        "ClusterRole": "clusterroles",
        "ClusterRoleBinding": "clusterrolebindings",
    }

    # Non-namespaced resources
    cluster_resources = {"Namespace", "Node", "PersistentVolume", "ClusterRole", "ClusterRoleBinding"}

    is_namespaced = kind not in cluster_resources

    if api_version == "v1" and kind in core_resources:
        resource = core_resources[kind]
        if is_namespaced:
            return f"/api/v1/namespaces/{quote(namespace, safe='')}/{resource}/{quote(name, safe='')}"
        else:
            return f"/api/v1/{resource}/{quote(name, safe='')}"

    elif api_version == "apps/v1" and kind in apps_resources:
        resource = apps_resources[kind]
        return f"/apis/apps/v1/namespaces/{quote(namespace, safe='')}/{resource}/{quote(name, safe='')}"

    elif api_version == "batch/v1" and kind in batch_resources:
        resource = batch_resources[kind]
        return f"/apis/batch/v1/namespaces/{quote(namespace, safe='')}/{resource}/{quote(name, safe='')}"

    elif api_version == "networking.k8s.io/v1" and kind in networking_resources:
        resource = networking_resources[kind]
        return f"/apis/networking.k8s.io/v1/namespaces/{quote(namespace, safe='')}/{resource}/{quote(name, safe='')}"

    elif api_version == "rbac.authorization.k8s.io/v1" and kind in rbac_resources:
        resource = rbac_resources[kind]
        if is_namespaced:
            return f"/apis/rbac.authorization.k8s.io/v1/namespaces/{quote(namespace, safe='')}/{resource}/{quote(name, safe='')}"
        else:
            return f"/apis/rbac.authorization.k8s.io/v1/{resource}/{quote(name, safe='')}"

    return None


def _is_namespaced(kind: str) -> bool:
    """Check if a resource kind is namespaced."""
    cluster_resources = {"Namespace", "Node", "PersistentVolume", "ClusterRole", "ClusterRoleBinding"}
    return kind not in cluster_resources


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_pods": list_pods,
    "get_pod": get_pod,
    "list_deployments": list_deployments,
    "scale_deployment": scale_deployment,
    "list_services": list_services,
    "list_namespaces": list_namespaces,
    "get_logs": get_logs,
    "apply_manifest": apply_manifest,
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
        logger.info(f"Executing kubernetes.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
