"""Server drain mode state management.

When a server receives SIGTERM, it enters drain mode before shutting down.
In drain mode:
- Health check returns 503 (nginx stops sending new traffic)
- New game creation is rejected
- Active games get final snapshots written
- All WebSocket connections are closed with code 4301
"""

import logging

logger = logging.getLogger(__name__)

_draining: bool = False


def is_draining() -> bool:
    """Check if the server is in drain mode."""
    return _draining


def set_draining(value: bool = True) -> None:
    """Set the drain mode flag."""
    global _draining
    _draining = value
    if value:
        logger.warning("Server entering drain mode")
