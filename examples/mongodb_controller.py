"""
MongoDB Atlas Controller for TinyHive

A controller for MongoDB Atlas Data API, providing CRUD operations
and aggregation pipelines through the Atlas Data API.

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

{
    "app_id": "data-xxxxx",
    "api_key_env": "MONGODB_API_KEY",
    "default_data_source": "Cluster0",
    "default_database": "mydb"
}

Required Fields:
- app_id: Your MongoDB Atlas Data API App ID

Optional Fields:
- api_key_env: Environment variable containing the API key (default: MONGODB_API_KEY)
- default_data_source: Default cluster name (optional, can be specified per-request)
- default_database: Default database name (optional, can be specified per-request)

API Key Setup:
--------------
1. In MongoDB Atlas, go to Data API and enable it for your cluster
2. Create an API key with appropriate permissions
3. Set the environment variable: export MONGODB_API_KEY="your-api-key"

Dependencies:
------------
None - uses Python standard library only (urllib.request)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger("tinyhive.controller.mongodb")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# MongoDB Atlas Data API base URL template
DATA_API_BASE_URL = "https://data.mongodb-api.com/app/{app_id}/endpoint/data/v1"

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
    """List available MongoDB profile names."""
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(PROFILES_DIR.glob("*.json"))]


# =============================================================================
# HTTP Helper
# =============================================================================

def _api_call(
    api_key: str,
    app_id: str,
    action: str,
    body: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make an authenticated MongoDB Atlas Data API call.

    Args:
        api_key: The MongoDB Atlas API key
        app_id: The Data API App ID
        action: The API action (e.g., 'findOne', 'insertOne')
        body: The request body as a dictionary
        timeout: Request timeout in seconds

    Returns:
        Dict with 'ok' status and either 'result'/'data' or 'error'
    """
    url = f"{DATA_API_BASE_URL.format(app_id=app_id)}/action/{action}"

    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
        "Accept": "application/json",
    }

    data = json.dumps(body).encode("utf-8")

    try:
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            if response_body:
                result = json.loads(response_body)
                return {"ok": True, "result": result}
            return {"ok": True, "result": {}}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_data = json.loads(error_body)
            error_message = error_data.get("error", error_body[:500])
        except json.JSONDecodeError:
            error_message = error_body[:500]
        logger.error("MongoDB API error %d: %s", e.code, error_message)
        return {"ok": False, "error": f"HTTP {e.code}: {error_message}"}
    except URLError as e:
        logger.error("Network error: %s", e.reason)
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        logger.exception("Unexpected error in MongoDB API call")
        return {"ok": False, "error": str(e)}


def _get_api_key(profile: Dict[str, Any]) -> str:
    """Get the API key from environment variable specified in profile."""
    env_var = profile.get("api_key_env", "MONGODB_API_KEY")
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(f"Environment variable '{env_var}' not set")
    return api_key


def _get_app_id(profile: Dict[str, Any]) -> str:
    """Get the App ID from profile."""
    app_id = profile.get("app_id")
    if not app_id:
        raise ValueError("Profile must specify 'app_id'")
    return app_id


# =============================================================================
# Actions
# =============================================================================

def find_one(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find a single document in a collection.

    Params:
        dataSource (str): The cluster name (optional, uses profile default)
        database (str): The database name (required or from profile default)
        collection (str): The collection name (required)
        filter (dict): Query filter (optional, default: {})
        projection (dict): Fields to include/exclude (optional)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    app_id = _get_app_id(profile)

    data_source = params.get("dataSource", profile.get("default_data_source"))
    database = params.get("database", profile.get("default_database"))
    collection = params.get("collection")

    if not data_source:
        return {"ok": False, "error": "dataSource is required (in params or profile default)"}
    if not database:
        return {"ok": False, "error": "database is required (in params or profile default)"}
    if not collection:
        return {"ok": False, "error": "collection is required"}

    body: Dict[str, Any] = {
        "dataSource": data_source,
        "database": database,
        "collection": collection,
        "filter": params.get("filter", {}),
    }

    if "projection" in params:
        body["projection"] = params["projection"]

    result = _api_call(api_key, app_id, "findOne", body)

    if result.get("ok") and "result" in result:
        document = result["result"].get("document")
        return {"ok": True, "data": document}
    return result


def find(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find multiple documents in a collection.

    Params:
        dataSource (str): The cluster name (optional, uses profile default)
        database (str): The database name (required or from profile default)
        collection (str): The collection name (required)
        filter (dict): Query filter (optional, default: {})
        projection (dict): Fields to include/exclude (optional)
        sort (dict): Sort specification (optional)
        limit (int): Maximum documents to return (optional)
        skip (int): Number of documents to skip (optional)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    app_id = _get_app_id(profile)

    data_source = params.get("dataSource", profile.get("default_data_source"))
    database = params.get("database", profile.get("default_database"))
    collection = params.get("collection")

    if not data_source:
        return {"ok": False, "error": "dataSource is required (in params or profile default)"}
    if not database:
        return {"ok": False, "error": "database is required (in params or profile default)"}
    if not collection:
        return {"ok": False, "error": "collection is required"}

    body: Dict[str, Any] = {
        "dataSource": data_source,
        "database": database,
        "collection": collection,
        "filter": params.get("filter", {}),
    }

    if "projection" in params:
        body["projection"] = params["projection"]
    if "sort" in params:
        body["sort"] = params["sort"]
    if "limit" in params:
        body["limit"] = params["limit"]
    if "skip" in params:
        body["skip"] = params["skip"]

    result = _api_call(api_key, app_id, "find", body)

    if result.get("ok") and "result" in result:
        documents = result["result"].get("documents", [])
        return {"ok": True, "data": documents, "count": len(documents)}
    return result


def insert_one(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Insert a single document into a collection.

    Params:
        dataSource (str): The cluster name (optional, uses profile default)
        database (str): The database name (required or from profile default)
        collection (str): The collection name (required)
        document (dict): The document to insert (required)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    app_id = _get_app_id(profile)

    data_source = params.get("dataSource", profile.get("default_data_source"))
    database = params.get("database", profile.get("default_database"))
    collection = params.get("collection")
    document = params.get("document")

    if not data_source:
        return {"ok": False, "error": "dataSource is required (in params or profile default)"}
    if not database:
        return {"ok": False, "error": "database is required (in params or profile default)"}
    if not collection:
        return {"ok": False, "error": "collection is required"}
    if not document:
        return {"ok": False, "error": "document is required"}

    body: Dict[str, Any] = {
        "dataSource": data_source,
        "database": database,
        "collection": collection,
        "document": document,
    }

    result = _api_call(api_key, app_id, "insertOne", body)

    if result.get("ok") and "result" in result:
        inserted_id = result["result"].get("insertedId")
        return {"ok": True, "result": {"insertedId": inserted_id}}
    return result


def insert_many(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Insert multiple documents into a collection.

    Params:
        dataSource (str): The cluster name (optional, uses profile default)
        database (str): The database name (required or from profile default)
        collection (str): The collection name (required)
        documents (list): List of documents to insert (required)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    app_id = _get_app_id(profile)

    data_source = params.get("dataSource", profile.get("default_data_source"))
    database = params.get("database", profile.get("default_database"))
    collection = params.get("collection")
    documents = params.get("documents")

    if not data_source:
        return {"ok": False, "error": "dataSource is required (in params or profile default)"}
    if not database:
        return {"ok": False, "error": "database is required (in params or profile default)"}
    if not collection:
        return {"ok": False, "error": "collection is required"}
    if not documents:
        return {"ok": False, "error": "documents is required"}
    if not isinstance(documents, list):
        return {"ok": False, "error": "documents must be a list"}

    body: Dict[str, Any] = {
        "dataSource": data_source,
        "database": database,
        "collection": collection,
        "documents": documents,
    }

    result = _api_call(api_key, app_id, "insertMany", body)

    if result.get("ok") and "result" in result:
        inserted_ids = result["result"].get("insertedIds", [])
        return {"ok": True, "result": {"insertedIds": inserted_ids, "insertedCount": len(inserted_ids)}}
    return result


def update_one(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a single document in a collection.

    Params:
        dataSource (str): The cluster name (optional, uses profile default)
        database (str): The database name (required or from profile default)
        collection (str): The collection name (required)
        filter (dict): Query filter to match the document (required)
        update (dict): Update operations to apply (required)
        upsert (bool): Insert if no document matches (optional, default: false)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    app_id = _get_app_id(profile)

    data_source = params.get("dataSource", profile.get("default_data_source"))
    database = params.get("database", profile.get("default_database"))
    collection = params.get("collection")
    filter_doc = params.get("filter")
    update_doc = params.get("update")

    if not data_source:
        return {"ok": False, "error": "dataSource is required (in params or profile default)"}
    if not database:
        return {"ok": False, "error": "database is required (in params or profile default)"}
    if not collection:
        return {"ok": False, "error": "collection is required"}
    if filter_doc is None:
        return {"ok": False, "error": "filter is required"}
    if not update_doc:
        return {"ok": False, "error": "update is required"}

    body: Dict[str, Any] = {
        "dataSource": data_source,
        "database": database,
        "collection": collection,
        "filter": filter_doc,
        "update": update_doc,
    }

    if "upsert" in params:
        body["upsert"] = params["upsert"]

    result = _api_call(api_key, app_id, "updateOne", body)

    if result.get("ok") and "result" in result:
        return {
            "ok": True,
            "result": {
                "matchedCount": result["result"].get("matchedCount", 0),
                "modifiedCount": result["result"].get("modifiedCount", 0),
                "upsertedId": result["result"].get("upsertedId"),
            }
        }
    return result


def update_many(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update multiple documents in a collection.

    Params:
        dataSource (str): The cluster name (optional, uses profile default)
        database (str): The database name (required or from profile default)
        collection (str): The collection name (required)
        filter (dict): Query filter to match documents (required)
        update (dict): Update operations to apply (required)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    app_id = _get_app_id(profile)

    data_source = params.get("dataSource", profile.get("default_data_source"))
    database = params.get("database", profile.get("default_database"))
    collection = params.get("collection")
    filter_doc = params.get("filter")
    update_doc = params.get("update")

    if not data_source:
        return {"ok": False, "error": "dataSource is required (in params or profile default)"}
    if not database:
        return {"ok": False, "error": "database is required (in params or profile default)"}
    if not collection:
        return {"ok": False, "error": "collection is required"}
    if filter_doc is None:
        return {"ok": False, "error": "filter is required"}
    if not update_doc:
        return {"ok": False, "error": "update is required"}

    body: Dict[str, Any] = {
        "dataSource": data_source,
        "database": database,
        "collection": collection,
        "filter": filter_doc,
        "update": update_doc,
    }

    result = _api_call(api_key, app_id, "updateMany", body)

    if result.get("ok") and "result" in result:
        return {
            "ok": True,
            "result": {
                "matchedCount": result["result"].get("matchedCount", 0),
                "modifiedCount": result["result"].get("modifiedCount", 0),
            }
        }
    return result


def delete_one(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a single document from a collection.

    Params:
        dataSource (str): The cluster name (optional, uses profile default)
        database (str): The database name (required or from profile default)
        collection (str): The collection name (required)
        filter (dict): Query filter to match the document (required)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    app_id = _get_app_id(profile)

    data_source = params.get("dataSource", profile.get("default_data_source"))
    database = params.get("database", profile.get("default_database"))
    collection = params.get("collection")
    filter_doc = params.get("filter")

    if not data_source:
        return {"ok": False, "error": "dataSource is required (in params or profile default)"}
    if not database:
        return {"ok": False, "error": "database is required (in params or profile default)"}
    if not collection:
        return {"ok": False, "error": "collection is required"}
    if filter_doc is None:
        return {"ok": False, "error": "filter is required"}

    body: Dict[str, Any] = {
        "dataSource": data_source,
        "database": database,
        "collection": collection,
        "filter": filter_doc,
    }

    result = _api_call(api_key, app_id, "deleteOne", body)

    if result.get("ok") and "result" in result:
        return {
            "ok": True,
            "result": {
                "deletedCount": result["result"].get("deletedCount", 0),
            }
        }
    return result


def delete_many(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete multiple documents from a collection.

    Params:
        dataSource (str): The cluster name (optional, uses profile default)
        database (str): The database name (required or from profile default)
        collection (str): The collection name (required)
        filter (dict): Query filter to match documents (required)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    app_id = _get_app_id(profile)

    data_source = params.get("dataSource", profile.get("default_data_source"))
    database = params.get("database", profile.get("default_database"))
    collection = params.get("collection")
    filter_doc = params.get("filter")

    if not data_source:
        return {"ok": False, "error": "dataSource is required (in params or profile default)"}
    if not database:
        return {"ok": False, "error": "database is required (in params or profile default)"}
    if not collection:
        return {"ok": False, "error": "collection is required"}
    if filter_doc is None:
        return {"ok": False, "error": "filter is required"}

    body: Dict[str, Any] = {
        "dataSource": data_source,
        "database": database,
        "collection": collection,
        "filter": filter_doc,
    }

    result = _api_call(api_key, app_id, "deleteMany", body)

    if result.get("ok") and "result" in result:
        return {
            "ok": True,
            "result": {
                "deletedCount": result["result"].get("deletedCount", 0),
            }
        }
    return result


def aggregate(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run an aggregation pipeline on a collection.

    Params:
        dataSource (str): The cluster name (optional, uses profile default)
        database (str): The database name (required or from profile default)
        collection (str): The collection name (required)
        pipeline (list): Aggregation pipeline stages (required)
    """
    profile = load_profile(profile_name)
    api_key = _get_api_key(profile)
    app_id = _get_app_id(profile)

    data_source = params.get("dataSource", profile.get("default_data_source"))
    database = params.get("database", profile.get("default_database"))
    collection = params.get("collection")
    pipeline = params.get("pipeline")

    if not data_source:
        return {"ok": False, "error": "dataSource is required (in params or profile default)"}
    if not database:
        return {"ok": False, "error": "database is required (in params or profile default)"}
    if not collection:
        return {"ok": False, "error": "collection is required"}
    if not pipeline:
        return {"ok": False, "error": "pipeline is required"}
    if not isinstance(pipeline, list):
        return {"ok": False, "error": "pipeline must be a list"}

    body: Dict[str, Any] = {
        "dataSource": data_source,
        "database": database,
        "collection": collection,
        "pipeline": pipeline,
    }

    result = _api_call(api_key, app_id, "aggregate", body)

    if result.get("ok") and "result" in result:
        documents = result["result"].get("documents", [])
        return {"ok": True, "data": documents, "count": len(documents)}
    return result


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "find_one": find_one,
    "find": find,
    "insert_one": insert_one,
    "insert_many": insert_many,
    "update_one": update_one,
    "update_many": update_many,
    "delete_one": delete_one,
    "delete_many": delete_many,
    "aggregate": aggregate,
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
        logger.info(f"Executing mongodb.{profile}.{action}")
        return ACTIONS[action](profile, params)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("Unexpected error executing action %s", action)
        return {"ok": False, "error": f"Internal error: {str(e)}"}
