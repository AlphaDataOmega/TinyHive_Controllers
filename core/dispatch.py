"""Controller Dispatch — job routing to controllers.

Polls the execution queue and dispatches jobs to registered controllers.
"""

import importlib.util
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from .runtime import ControllerRuntime

log = logging.getLogger("tinyhive.controller.dispatch")

# Controller registry: type -> (loader_func, signature_type)
# signature_type: "profile_action" or "action_only"
CONTROLLER_REGISTRY: Dict[str, Tuple[Callable, str]] = {}


def register_controller(
    controller_type: str,
    loader: Callable[[], Any],
    signature: str = "profile_action"
) -> None:
    """Register a controller type.

    Args:
        controller_type: Type name (e.g., "ssh", "hub")
        loader: Function that returns the controller module
        signature: "profile_action" for execute(profile, action, params)
                   "action_only" for execute(action, params)
    """
    CONTROLLER_REGISTRY[controller_type] = (loader, signature)


def _load_controller_from_path(path: Path) -> Any:
    """Dynamically load a controller module from path."""
    spec = importlib.util.spec_from_file_location("controller", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load controller from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ControllerDispatch:
    """Dispatch service that processes the execution queue."""

    def __init__(
        self,
        runtime: ControllerRuntime,
        controllers_dir: Optional[Path] = None,
        poll_interval: float = 1.0,
    ):
        self.runtime = runtime
        self.controllers_dir = controllers_dir or Path("controllers")
        self.poll_interval = poll_interval
        self._running = False

    def _get_controller(self, controller_type: str) -> Tuple[Any, str]:
        """Get a controller module by type."""
        # Check registry first
        if controller_type in CONTROLLER_REGISTRY:
            loader, signature = CONTROLLER_REGISTRY[controller_type]
            return loader(), signature

        # Try to auto-discover from controllers directory
        controller_dir = self.controllers_dir / f"controller_{controller_type}"
        projects_dir = controller_dir / "projects"

        if projects_dir.exists():
            # Look for {type}.py
            controller_file = projects_dir / f"{controller_type}.py"
            if controller_file.exists():
                module = _load_controller_from_path(controller_file)
                # Determine signature from module
                signature = "action_only" if controller_type == "hub" else "profile_action"
                return module, signature

        raise ValueError(f"Unknown controller type: {controller_type}")

    def dispatch_one(self, execution_id: int) -> Dict[str, Any]:
        """Dispatch a single execution."""
        status = self.runtime.get_status(execution_id)
        if not status:
            return {"ok": False, "error": "Execution not found"}

        if status["status"] != "queued":
            return {"ok": False, "error": f"Execution status is {status['status']}"}

        method_id = status["method_id"]
        params = status["params"]

        # Parse method_id
        parts = method_id.split(".")
        if len(parts) != 4:
            self.runtime.fail(execution_id, f"Invalid method_id: {method_id}")
            return {"ok": False, "error": f"Invalid method_id: {method_id}"}

        controller_type = parts[1]
        profile = parts[2]
        action = parts[3]

        # Mark as executing
        self.runtime.execute(execution_id)

        try:
            # Get controller
            module, signature = self._get_controller(controller_type)

            # Dispatch
            if signature == "profile_action":
                result = module.execute(profile, action, params)
            else:  # action_only
                result = module.execute(action, params)

            # Complete
            self.runtime.complete(execution_id, result)
            return {"ok": True, "result": result}

        except Exception as e:
            error = str(e)
            log.exception(f"Controller {controller_type} failed: {error}")
            self.runtime.fail(execution_id, error)
            return {"ok": False, "error": error}

    def process_queue(self) -> int:
        """Process all queued items. Returns count processed."""
        items = self.runtime.list_queue(status="queued")
        processed = 0

        for item in items:
            result = self.dispatch_one(item["id"])
            processed += 1
            log.info(f"Processed {item['method_id']}: {result.get('ok')}")

        return processed

    def run(self) -> None:
        """Run the dispatch loop."""
        self._running = True
        log.info(f"Starting controller dispatch (interval: {self.poll_interval}s)")

        while self._running:
            try:
                count = self.process_queue()
                if count > 0:
                    log.debug(f"Processed {count} items")
            except Exception as e:
                log.exception(f"Dispatch error: {e}")

            time.sleep(self.poll_interval)

    def stop(self) -> None:
        """Stop the dispatch loop."""
        self._running = False


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Controller dispatch service")
    parser.add_argument("--db", default="controller_runtime.db", help="Database path")
    parser.add_argument("--controllers", default="controllers", help="Controllers directory")
    parser.add_argument("--interval", type=float, default=1.0, help="Poll interval")
    parser.add_argument("--once", action="store_true", help="Process once and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    runtime = ControllerRuntime(db_path=Path(args.db))
    dispatch = ControllerDispatch(
        runtime=runtime,
        controllers_dir=Path(args.controllers),
        poll_interval=args.interval,
    )

    if args.once:
        count = dispatch.process_queue()
        print(f"Processed {count} items")
    else:
        try:
            dispatch.run()
        except KeyboardInterrupt:
            dispatch.stop()


if __name__ == "__main__":
    main()
