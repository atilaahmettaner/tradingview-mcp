"""MCP Apps bridge for the pinned 1.x python SDK.

The MCP Apps extension (interactive HTML views rendered by the host) is
plain wire-format, not framework magic. A host that supports it looks for
three JSON fields:

  1. ``extensions["io.modelcontextprotocol/ui"]`` in the server's
     initialize capabilities,
  2. ``_meta.ui.resourceUri`` on a tool advertised by tools/list,
  3. a resource whose mimeType is ``text/html;profile=mcp-app`` (plus an
     optional ``_meta.ui.csp`` allow-list for external assets).

FastMCP 4 exposes all of this as ``AppConfig``; the 1.x SDK this project is
pinned to (``mcp<2`` — 2.x removed ``mcp.server.fastmcp`` and broke clients)
has no such API, but its pydantic models already carry the ``_meta`` /
``extensions`` fields. So this shim post-processes the three relevant
responses on the low-level server FastMCP drives. Delete it if the project
ever migrates to a framework with first-class Apps support.
"""
from __future__ import annotations

from typing import Any

from mcp import types
from mcp.server.fastmcp import FastMCP


def enable_apps(
    mcp: FastMCP,
    tool_ui: dict[str, str],
    resource_meta: dict[str, dict[str, Any]],
) -> None:
    """Advertise the Apps extension and stamp ui metadata onto the wire.

    tool_ui:        tool name -> ui:// resource uri rendered for its results.
    resource_meta:  resource uri -> _meta dict (csp allow-list etc.).
    """
    srv = mcp._mcp_server

    # 1. initialize capabilities — advertise the ui extension.
    orig_caps = srv.get_capabilities

    def get_capabilities(*args: Any, **kwargs: Any) -> types.ServerCapabilities:
        caps = orig_caps(*args, **kwargs)
        # `extensions` is not a declared field on this SDK's ServerCapabilities —
        # it rides as a pydantic extra (the model allows and serializes extras).
        # Reading it as a plain attribute raises AttributeError, so use getattr;
        # plain assignment stores an extra just fine.
        existing = getattr(caps, "extensions", None) or {}
        caps.extensions = {**existing, "io.modelcontextprotocol/ui": {}}
        return caps

    srv.get_capabilities = get_capabilities  # type: ignore[method-assign]

    # 2 & 3. tools/list and resources/list — inject _meta. The handlers are
    # registered by FastMCP at construction time, keyed by request type.
    def _stamp(obj: Any, meta: dict[str, Any]) -> None:
        merged = {**(getattr(obj, "meta", None) or {}), **meta}
        try:
            obj.meta = merged
        except Exception:  # pydantic frozen/validate_assignment fallback
            object.__setattr__(obj, "meta", merged)

    orig_list_tools = srv.request_handlers[types.ListToolsRequest]

    async def list_tools(req: types.ListToolsRequest) -> types.ServerResult:
        result = await orig_list_tools(req)
        for tool in result.root.tools:
            uri = tool_ui.get(tool.name)
            if uri:
                _stamp(tool, {"ui": {"resourceUri": uri}})
        return result

    srv.request_handlers[types.ListToolsRequest] = list_tools

    orig_list_resources = srv.request_handlers[types.ListResourcesRequest]

    async def list_resources(req: types.ListResourcesRequest) -> types.ServerResult:
        result = await orig_list_resources(req)
        for res in result.root.resources:
            meta = resource_meta.get(str(res.uri))
            if meta:
                _stamp(res, meta)
        return result

    srv.request_handlers[types.ListResourcesRequest] = list_resources
