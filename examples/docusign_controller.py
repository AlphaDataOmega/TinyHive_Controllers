"""DocuSign Controller - DocuSign eSignature REST API integration.

This controller provides integration with the DocuSign eSignature REST API
for managing electronic signature workflows, envelopes, and documents.

Method IDs:
  controller.docusign.{profile}.create_envelope
  controller.docusign.{profile}.get_envelope
  controller.docusign.{profile}.list_envelopes
  controller.docusign.{profile}.void_envelope
  controller.docusign.{profile}.download_document
  controller.docusign.{profile}.get_recipients
  controller.docusign.{profile}.create_from_template
  controller.docusign.{profile}.resend_envelope

Profile Configuration:
  Profiles are JSON files in profiles/ directory with the following fields:

  {
    "account_id": "your-docusign-account-id",
    "token_env": "DOCUSIGN_ACCESS_TOKEN",
    "base_url": "https://demo.docusign.net/restapi/v2.1"
  }

  For production use:
  {
    "account_id": "your-docusign-account-id",
    "token_env": "DOCUSIGN_ACCESS_TOKEN",
    "base_url": "https://na2.docusign.net/restapi/v2.1"
  }

Required OAuth Scopes:
  - signature: Basic eSignature operations
  - extended: Extended operations (void, etc.)
  - impersonation: If using JWT Grant for user impersonation

Dependencies:
  - None (standard library only)
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

logger = logging.getLogger("tinyhive.controller.docusign")

WORKSPACE = Path(__file__).resolve().parent.parent
PROFILES_DIR = WORKSPACE / "profiles"

DEFAULT_TIMEOUT = 60
DEFAULT_BASE_URL = "https://demo.docusign.net/restapi/v2.1"


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile configuration."""
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown profile '{name}'. Create {path} with DocuSign configuration.")
    return json.loads(path.read_text())


def list_profiles() -> List[str]:
    """List available DocuSign profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# HTTP Helpers
# =============================================================================

def _get_access_token(profile: Dict[str, Any]) -> str:
    """Get the access token from environment variable."""
    env_var = profile.get("token_env", "DOCUSIGN_ACCESS_TOKEN")
    token = os.environ.get(env_var, "")
    if not token:
        raise ValueError(
            f"Environment variable '{env_var}' not set. "
            "Obtain an access token from DocuSign OAuth flow."
        )
    return token


def _api_call(
    token: str,
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    content_type: str = "application/json",
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[Dict[str, str]] = None,
    raw_response: bool = False
) -> Dict[str, Any]:
    """Make an authenticated DocuSign API call."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }
    if extra_headers:
        headers.update(extra_headers)

    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read()
            if raw_response:
                return {"ok": True, "data": response_body}
            if response_body:
                return {"ok": True, "result": json.loads(response_body.decode("utf-8"))}
            return {"ok": True, "result": {"status": "success"}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("message", error_data.get("errorCode", error_body[:500]))
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("DocuSign API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in DocuSign API call")
        return {"ok": False, "error": str(e)}


def _build_url(profile: Dict[str, Any], endpoint: str) -> str:
    """Build the full API URL for an endpoint."""
    base_url = profile.get("base_url", DEFAULT_BASE_URL).rstrip("/")
    account_id = profile.get("account_id")
    if not account_id:
        raise ValueError("account_id required in profile")
    return f"{base_url}/accounts/{account_id}/{endpoint.lstrip('/')}"


# =============================================================================
# Actions
# =============================================================================

def create_envelope(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create and optionally send an envelope.

    Params:
        email_subject (str): Subject line for the email (required)
        recipients (dict): Recipients object containing signers, cc, etc. (required)
            Example: {
                "signers": [
                    {
                        "email": "signer@example.com",
                        "name": "John Doe",
                        "recipientId": "1",
                        "routingOrder": "1",
                        "tabs": {...}  # Optional signing tabs
                    }
                ],
                "carbonCopies": [...]
            }
        documents (list): List of document objects (required)
            Example: [
                {
                    "documentId": "1",
                    "name": "Contract.pdf",
                    "fileExtension": "pdf",
                    "documentBase64": "<base64-encoded-content>"
                }
            ]
        status (str): "created" (draft) or "sent" (default: "sent")
        email_blurb (str): Email body text (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    email_subject = params.get("email_subject")
    recipients = params.get("recipients")
    documents = params.get("documents")
    status = params.get("status", "sent")
    email_blurb = params.get("email_blurb", "")

    if not email_subject:
        return {"ok": False, "error": "email_subject required"}
    if not recipients:
        return {"ok": False, "error": "recipients required"}
    if not documents:
        return {"ok": False, "error": "documents required"}

    envelope_definition = {
        "emailSubject": email_subject,
        "documents": documents,
        "recipients": recipients,
        "status": status,
    }
    if email_blurb:
        envelope_definition["emailBlurb"] = email_blurb

    url = _build_url(profile, "envelopes")
    data = json.dumps(envelope_definition).encode("utf-8")

    result = _api_call(token, url, method="POST", data=data)

    if result.get("ok") and "result" in result:
        envelope = result["result"]
        return {
            "ok": True,
            "result": {
                "envelope_id": envelope.get("envelopeId"),
                "status": envelope.get("status"),
                "status_date_time": envelope.get("statusDateTime"),
                "uri": envelope.get("uri"),
            }
        }
    return result


def get_envelope(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get envelope status and details.

    Params:
        envelope_id (str): The envelope ID (required)
        include (str): Additional info to include (optional)
            Options: "custom_fields", "documents", "attachments", "extensions",
                     "folders", "recipients", "powerform", "tabs", "payment_tabs"
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    envelope_id = params.get("envelope_id")
    if not envelope_id:
        return {"ok": False, "error": "envelope_id required"}

    endpoint = f"envelopes/{envelope_id}"
    query_params = {}
    if params.get("include"):
        query_params["include"] = params["include"]

    url = _build_url(profile, endpoint)
    if query_params:
        url += "?" + urlencode(query_params)

    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        envelope = result["result"]
        return {
            "ok": True,
            "result": {
                "envelope_id": envelope.get("envelopeId"),
                "status": envelope.get("status"),
                "email_subject": envelope.get("emailSubject"),
                "email_blurb": envelope.get("emailBlurb"),
                "created_date_time": envelope.get("createdDateTime"),
                "sent_date_time": envelope.get("sentDateTime"),
                "completed_date_time": envelope.get("completedDateTime"),
                "voided_date_time": envelope.get("voidedDateTime"),
                "voided_reason": envelope.get("voidedReason"),
                "sender": envelope.get("sender"),
                "recipients_uri": envelope.get("recipientsUri"),
                "documents_uri": envelope.get("documentsUri"),
            }
        }
    return result


def list_envelopes(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List envelopes with optional filters.

    Params:
        from_date (str): Start date in ISO 8601 format (required)
            Example: "2024-01-01T00:00:00Z"
        to_date (str): End date in ISO 8601 format (optional)
        status (str): Filter by status (optional)
            Options: "completed", "created", "declined", "delivered", "sent",
                     "signed", "voided", "deleted", "processing"
        folder_types (str): Folder types to include (optional)
            Options: "inbox", "sentitems", "draft", "recyclebin"
        count (int): Maximum envelopes to return (default: 25, max: 100)
        start_position (int): Starting position for pagination (optional)
        search_text (str): Search envelope metadata (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    from_date = params.get("from_date")
    if not from_date:
        return {"ok": False, "error": "from_date required"}

    query_params = {"from_date": from_date}

    if params.get("to_date"):
        query_params["to_date"] = params["to_date"]
    if params.get("status"):
        query_params["status"] = params["status"]
    if params.get("folder_types"):
        query_params["folder_types"] = params["folder_types"]
    if params.get("count"):
        query_params["count"] = str(params["count"])
    if params.get("start_position"):
        query_params["start_position"] = str(params["start_position"])
    if params.get("search_text"):
        query_params["search_text"] = params["search_text"]

    url = _build_url(profile, "envelopes") + "?" + urlencode(query_params)

    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        data = result["result"]
        envelopes = data.get("envelopes", [])
        return {
            "ok": True,
            "result": {
                "envelopes": [
                    {
                        "envelope_id": e.get("envelopeId"),
                        "status": e.get("status"),
                        "email_subject": e.get("emailSubject"),
                        "created_date_time": e.get("createdDateTime"),
                        "sent_date_time": e.get("sentDateTime"),
                        "completed_date_time": e.get("completedDateTime"),
                    }
                    for e in envelopes
                ],
                "total_set_size": data.get("totalSetSize"),
                "result_set_size": data.get("resultSetSize"),
                "start_position": data.get("startPosition"),
                "end_position": data.get("endPosition"),
            }
        }
    return result


def void_envelope(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Void an envelope. Only envelopes in 'sent' or 'delivered' status can be voided.

    Params:
        envelope_id (str): The envelope ID (required)
        void_reason (str): Reason for voiding (required)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    envelope_id = params.get("envelope_id")
    void_reason = params.get("void_reason")

    if not envelope_id:
        return {"ok": False, "error": "envelope_id required"}
    if not void_reason:
        return {"ok": False, "error": "void_reason required"}

    url = _build_url(profile, f"envelopes/{envelope_id}")
    data = json.dumps({
        "status": "voided",
        "voidedReason": void_reason
    }).encode("utf-8")

    result = _api_call(token, url, method="PUT", data=data)

    if result.get("ok"):
        return {
            "ok": True,
            "result": {
                "envelope_id": envelope_id,
                "status": "voided",
                "void_reason": void_reason,
            }
        }
    return result


def download_document(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Download a document from an envelope.

    Params:
        envelope_id (str): The envelope ID (required)
        document_id (str): The document ID (required)
            Use "combined" to get all documents in one PDF
            Use "certificate" to get the certificate of completion
            Use "archive" to get a ZIP of all documents
        local_path (str): Path to save the document (optional)
            If not provided, returns base64-encoded content
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    envelope_id = params.get("envelope_id")
    document_id = params.get("document_id")
    local_path = params.get("local_path")

    if not envelope_id:
        return {"ok": False, "error": "envelope_id required"}
    if not document_id:
        return {"ok": False, "error": "document_id required"}

    url = _build_url(profile, f"envelopes/{envelope_id}/documents/{document_id}")

    result = _api_call(
        token, url,
        content_type="application/pdf",
        raw_response=True
    )

    if result.get("ok") and "data" in result:
        doc_data = result["data"]

        if local_path:
            path = Path(local_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(doc_data)
            return {
                "ok": True,
                "result": {
                    "path": str(path),
                    "size": len(doc_data),
                    "envelope_id": envelope_id,
                    "document_id": document_id,
                }
            }
        else:
            return {
                "ok": True,
                "result": {
                    "data": base64.b64encode(doc_data).decode("ascii"),
                    "encoding": "base64",
                    "size": len(doc_data),
                    "envelope_id": envelope_id,
                    "document_id": document_id,
                }
            }
    return result


def get_recipients(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get recipients for an envelope.

    Params:
        envelope_id (str): The envelope ID (required)
        include_tabs (bool): Include tab (field) information (default: False)
        include_extended (bool): Include extended info (default: False)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    envelope_id = params.get("envelope_id")
    if not envelope_id:
        return {"ok": False, "error": "envelope_id required"}

    query_params = {}
    if params.get("include_tabs"):
        query_params["include_tabs"] = "true"
    if params.get("include_extended"):
        query_params["include_extended"] = "true"

    url = _build_url(profile, f"envelopes/{envelope_id}/recipients")
    if query_params:
        url += "?" + urlencode(query_params)

    result = _api_call(token, url)

    if result.get("ok") and "result" in result:
        data = result["result"]

        def format_recipient(r: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "recipient_id": r.get("recipientId"),
                "recipient_type": r.get("recipientType"),
                "email": r.get("email"),
                "name": r.get("name"),
                "status": r.get("status"),
                "routing_order": r.get("routingOrder"),
                "signed_date_time": r.get("signedDateTime"),
                "delivered_date_time": r.get("deliveredDateTime"),
                "declined_date_time": r.get("declinedDateTime"),
                "declined_reason": r.get("declinedReason"),
            }

        return {
            "ok": True,
            "result": {
                "signers": [format_recipient(s) for s in data.get("signers", [])],
                "carbon_copies": [format_recipient(c) for c in data.get("carbonCopies", [])],
                "certified_deliveries": [format_recipient(c) for c in data.get("certifiedDeliveries", [])],
                "in_person_signers": [format_recipient(i) for i in data.get("inPersonSigners", [])],
                "agents": [format_recipient(a) for a in data.get("agents", [])],
                "editors": [format_recipient(e) for e in data.get("editors", [])],
                "intermediaries": [format_recipient(i) for i in data.get("intermediaries", [])],
                "recipient_count": data.get("recipientCount"),
                "current_routing_order": data.get("currentRoutingOrder"),
            }
        }
    return result


def create_from_template(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an envelope from a template.

    Params:
        template_id (str): The template ID (required)
        recipients (dict): Template role assignments (required)
            Example: {
                "signers": [
                    {
                        "email": "signer@example.com",
                        "name": "John Doe",
                        "roleName": "Signer 1"  # Must match template role
                    }
                ],
                "carbonCopies": [...]
            }
        email_subject (str): Override template email subject (optional)
        email_blurb (str): Override template email body (optional)
        status (str): "created" (draft) or "sent" (default: "sent")
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    template_id = params.get("template_id")
    recipients = params.get("recipients")
    status = params.get("status", "sent")

    if not template_id:
        return {"ok": False, "error": "template_id required"}
    if not recipients:
        return {"ok": False, "error": "recipients required"}

    envelope_definition = {
        "templateId": template_id,
        "templateRoles": [],
        "status": status,
    }

    # Convert recipients to templateRoles format
    for signer in recipients.get("signers", []):
        envelope_definition["templateRoles"].append({
            "email": signer.get("email"),
            "name": signer.get("name"),
            "roleName": signer.get("roleName", signer.get("role_name")),
            "tabs": signer.get("tabs"),
        })
    for cc in recipients.get("carbonCopies", recipients.get("carbon_copies", [])):
        envelope_definition["templateRoles"].append({
            "email": cc.get("email"),
            "name": cc.get("name"),
            "roleName": cc.get("roleName", cc.get("role_name")),
        })

    if params.get("email_subject"):
        envelope_definition["emailSubject"] = params["email_subject"]
    if params.get("email_blurb"):
        envelope_definition["emailBlurb"] = params["email_blurb"]

    url = _build_url(profile, "envelopes")
    data = json.dumps(envelope_definition).encode("utf-8")

    result = _api_call(token, url, method="POST", data=data)

    if result.get("ok") and "result" in result:
        envelope = result["result"]
        return {
            "ok": True,
            "result": {
                "envelope_id": envelope.get("envelopeId"),
                "status": envelope.get("status"),
                "status_date_time": envelope.get("statusDateTime"),
                "template_id": template_id,
                "uri": envelope.get("uri"),
            }
        }
    return result


def resend_envelope(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resend envelope notifications to recipients who have not yet completed.

    Params:
        envelope_id (str): The envelope ID (required)
        resend_reason (str): Reason for resending (optional)
    """
    profile = load_profile(profile_name)
    token = _get_access_token(profile)

    envelope_id = params.get("envelope_id")
    if not envelope_id:
        return {"ok": False, "error": "envelope_id required"}

    # Update recipients with resend flag
    url = _build_url(profile, f"envelopes/{envelope_id}") + "?resend_envelope=true"

    result = _api_call(token, url, method="PUT", data=b"{}")

    if result.get("ok"):
        return {
            "ok": True,
            "result": {
                "envelope_id": envelope_id,
                "resent": True,
                "message": "Envelope notifications have been resent to pending recipients.",
            }
        }
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "create_envelope": create_envelope,
    "get_envelope": get_envelope,
    "list_envelopes": list_envelopes,
    "void_envelope": void_envelope,
    "download_document": download_document,
    "get_recipients": get_recipients,
    "create_from_template": create_from_template,
    "resend_envelope": resend_envelope,
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
        logger.info(f"Executing docusign.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
