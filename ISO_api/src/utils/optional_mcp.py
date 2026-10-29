"""Keep the HTTP API available when the optional MCP adapter is incompatible."""

import logging
import os

logger = logging.getLogger(__name__)


def mount_optional_mcp(app, factory):
    try:
        adapter = factory(app, name="My API MCP", description="MCP server for my API")
        adapter.mount()
        return adapter
    except TypeError:
        if os.getenv("ISO_MCP_STRICT", "0") == "1":
            raise
        logger.exception("MCP initialization failed (dependency API mismatch). MCP is unavailable; HTTP API remains enabled. Set ISO_MCP_STRICT=1 to fail startup instead.")
        return None
