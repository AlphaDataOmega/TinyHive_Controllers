"""Playwright controller — mobile-emulated browser automation.

All browsing uses iPhone 14 viewport (390x844) for smaller screenshots
and simpler page layouts. Screenshots are ephemeral — deleted after
the requesting agent processes them.

Pre-installed site profiles with flows live in projects/sites/.
Structure:
  projects/sites/{site}/
    site.json         — base URL, selectors, login info key
    flows/            — step-by-step action sequences
      sign_in.json
      send_post.json
      check_dms.json
    pages/            — page-specific selectors and landmarks
      home.json
      inbox.json

Method IDs:
  controller.playwright.{site}.navigate
  controller.playwright.{site}.screenshot
  controller.playwright.{site}.run_flow
  controller.playwright.{site}.extract_text
  controller.playwright.{site}.click
  controller.playwright.{site}.fill
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger("tinyhive.controller.playwright")

WORKSPACE = Path(__file__).resolve().parent.parent
SITES_DIR = WORKSPACE / "projects" / "sites"
SCREENSHOTS_DIR = WORKSPACE / "scratch" / "screenshots"

# Mobile emulation — iPhone 14
MOBILE_VIEWPORT = {"width": 390, "height": 844}
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)
MOBILE_DEVICE_SCALE_FACTOR = 3
MOBILE_IS_MOBILE = True
MOBILE_HAS_TOUCH = True


# ---------------------------------------------------------------------------
# Site profile management
# ---------------------------------------------------------------------------

def load_site(name: str) -> Dict[str, Any]:
    """Load a site profile from projects/sites/{name}/site.json."""
    site_dir = SITES_DIR / name
    site_json = site_dir / "site.json"
    if not site_json.exists():
        raise ValueError(f"Unknown site '{name}'. Available: {list_sites()}")
    return json.loads(site_json.read_text())


def list_sites() -> List[str]:
    """List available site profile names."""
    if not SITES_DIR.exists():
        return []
    return sorted(d.name for d in SITES_DIR.iterdir() if d.is_dir() and (d / "site.json").exists())


def load_flow(site: str, flow_name: str) -> Dict[str, Any]:
    """Load a flow definition from projects/sites/{site}/flows/{flow}.json."""
    flow_path = SITES_DIR / site / "flows" / f"{flow_name}.json"
    if not flow_path.exists():
        available = list_flows(site)
        raise ValueError(f"Unknown flow '{flow_name}' for site '{site}'. Available: {available}")
    return json.loads(flow_path.read_text())


def list_flows(site: str) -> List[str]:
    """List available flows for a site."""
    flows_dir = SITES_DIR / site / "flows"
    if not flows_dir.exists():
        return []
    return sorted(p.stem for p in flows_dir.glob("*.json"))


def load_page(site: str, page_name: str) -> Dict[str, Any]:
    """Load page selectors from projects/sites/{site}/pages/{page}.json."""
    page_path = SITES_DIR / site / "pages" / f"{page_name}.json"
    if not page_path.exists():
        return {}
    return json.loads(page_path.read_text())


# ---------------------------------------------------------------------------
# Screenshot management (ephemeral)
# ---------------------------------------------------------------------------

def _screenshot_path(site: str, label: str = "") -> Path:
    """Generate a screenshot path. All screenshots are ephemeral."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    name = f"{ts}_{site}_{label}.png" if label else f"{ts}_{site}.png"
    return SCREENSHOTS_DIR / name


def cleanup_screenshots(max_age_seconds: int = 300) -> int:
    """Delete screenshots older than max_age. Returns count deleted."""
    if not SCREENSHOTS_DIR.exists():
        return 0
    now = time.time()
    deleted = 0
    for f in SCREENSHOTS_DIR.glob("*.png"):
        if now - f.stat().st_mtime > max_age_seconds:
            f.unlink()
            deleted += 1
    return deleted


# ---------------------------------------------------------------------------
# Actions (Playwright MCP integration points)
#
# These functions build command dicts that BODY dispatches to the
# Playwright MCP server. They don't call Playwright directly —
# the MCP bridge handles that.
# ---------------------------------------------------------------------------

def navigate(site_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Navigate to a URL within a site's domain.

    Params:
        - url: URL to navigate to (default: site's base_url)
        - page: Page name to load URL from pages/{page}.json
    """
    site = load_site(site_name)
    url = params.get("url", site.get("base_url", ""))
    page = params.get("page")

    if page:
        page_data = load_page(site_name, page)
        url = page_data.get("url", url)

    return {
        "ok": True,
        "mcp_action": "browser_navigate",
        "mcp_params": {
            "url": url,
            "viewport": MOBILE_VIEWPORT,
            "userAgent": MOBILE_USER_AGENT,
            "deviceScaleFactor": MOBILE_DEVICE_SCALE_FACTOR,
            "isMobile": MOBILE_IS_MOBILE,
            "hasTouch": MOBILE_HAS_TOUCH,
        },
    }


def screenshot(site_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Take a screenshot. Path is returned for agent to read then delete.

    Params:
        - label: Optional label for the screenshot filename
        - full_page: Whether to capture full page (default: false)
    """
    label = params.get("label", "")
    path = _screenshot_path(site_name, label)

    return {
        "ok": True,
        "mcp_action": "browser_screenshot",
        "mcp_params": {
            "path": str(path),
            "fullPage": params.get("full_page", False),
        },
        "screenshot_path": str(path),
        "ephemeral": True,
    }


def run_flow(site_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a pre-defined flow (sequence of browser actions).

    Flow format:
    {
      "name": "sign_in",
      "description": "Sign into the site",
      "steps": [
        {"action": "navigate", "params": {"url": "https://..."}},
        {"action": "fill", "params": {"selector": "#email", "value": "$secrets.email"}},
        {"action": "fill", "params": {"selector": "#password", "value": "$secrets.password"}},
        {"action": "click", "params": {"selector": "button[type=submit]"}},
        {"action": "screenshot", "params": {"label": "post_login"}}
      ]
    }

    $secrets.{key} references are resolved from SecretsStore at runtime.

    Params:
        - flow: Flow name (required)
    """
    flow_name = params.get("flow", "")
    try:
        flow = load_flow(site_name, flow_name)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    steps = flow.get("steps", [])

    return {
        "ok": True,
        "flow": flow_name,
        "site": site_name,
        "steps_total": len(steps),
        "steps": steps,
        "description": flow.get("description", ""),
        "requires_secrets": any(
            "$secrets." in json.dumps(s.get("params", {}))
            for s in steps
        ),
    }


def extract_text(site_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Extract text content from a selector.

    Params:
        - selector: CSS selector (default: "body")
    """
    selector = params.get("selector", "body")
    return {
        "ok": True,
        "mcp_action": "browser_evaluate",
        "mcp_params": {
            "expression": f"document.querySelector('{selector}')?.innerText || ''",
        },
    }


def click(site_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Click an element.

    Params:
        - selector: CSS selector (required)
    """
    selector = params.get("selector", "")
    if not selector:
        return {"ok": False, "error": "selector required"}
    return {
        "ok": True,
        "mcp_action": "browser_click",
        "mcp_params": {"selector": selector},
    }


def fill(site_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Fill a form field.

    Params:
        - selector: CSS selector (required)
        - value: Value to fill (can reference $secrets.key)
    """
    selector = params.get("selector", "")
    value = params.get("value", "")
    if not selector:
        return {"ok": False, "error": "selector required"}
    return {
        "ok": True,
        "mcp_action": "browser_fill",
        "mcp_params": {"selector": selector, "value": value},
    }


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------

ACTIONS = {
    "navigate": navigate,
    "screenshot": screenshot,
    "run_flow": run_flow,
    "extract_text": extract_text,
    "click": click,
    "fill": fill,
}


def execute(site: str, action: str, params: Dict[str, Any]) -> Any:
    """Dispatch an action by name with a site profile."""
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action '{action}'. Available: {list(ACTIONS.keys())}"}
    return ACTIONS[action](site, params)
