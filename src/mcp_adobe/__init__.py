"""Adobe Creative MCP gateway core."""

from .core import (
    AdapterInfo,
    CapabilityRegistry,
    CreativeAdapter,
    ExecutionPolicy,
    PolicyError,
    RiskClass,
)
from .illustrator import IllustratorAdapter
from .mcp_stdio import (
    McpSubprocessToolClient,
    SubprocessMcpConfig,
    UpstreamToolError,
    illustrator_stdio_config,
    photoshop_stdio_config,
)
from .photoshop import OperationUnknownError, PhotoshopAdapter, UpstreamToolClient
from .xd import XdAdapter
from .xd_bridge import XdWebSocketBridgeClient

__all__ = [
    "AdapterInfo",
    "CapabilityRegistry",
    "CreativeAdapter",
    "ExecutionPolicy",
    "IllustratorAdapter",
    "McpSubprocessToolClient",
    "OperationUnknownError",
    "PhotoshopAdapter",
    "PolicyError",
    "RiskClass",
    "SubprocessMcpConfig",
    "UpstreamToolClient",
    "UpstreamToolError",
    "XdAdapter",
    "XdWebSocketBridgeClient",
    "illustrator_stdio_config",
    "photoshop_stdio_config",
]
