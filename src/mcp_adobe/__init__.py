"""Adobe Creative MCP gateway core."""

from .core import (
    AdapterInfo,
    CapabilityRegistry,
    CreativeAdapter,
    ExecutionPolicy,
    PolicyError,
    RiskClass,
)
from .mcp_stdio import (
    McpSubprocessToolClient,
    SubprocessMcpConfig,
    UpstreamToolError,
    illustrator_stdio_config,
    photoshop_stdio_config,
)
from .photoshop import OperationUnknownError, PhotoshopAdapter, UpstreamToolClient

__all__ = [
    "AdapterInfo",
    "CapabilityRegistry",
    "CreativeAdapter",
    "ExecutionPolicy",
    "McpSubprocessToolClient",
    "OperationUnknownError",
    "PhotoshopAdapter",
    "PolicyError",
    "RiskClass",
    "SubprocessMcpConfig",
    "UpstreamToolClient",
    "UpstreamToolError",
    "illustrator_stdio_config",
    "photoshop_stdio_config",
]
