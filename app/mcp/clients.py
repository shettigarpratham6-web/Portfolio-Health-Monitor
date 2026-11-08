"""
AgentX – Portfolio Health Monitor
MCP Client Gateway
Connects to the three independent MCP servers and exposes tools to LangGraph & Agent Workflows
"""

import asyncio
from functools import lru_cache
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from langchain_core.tools import StructuredTool
from langsmith import traceable
from mcp.server.fastmcp import FastMCP

from app.mcp.servers.analysis_server import analysis_mcp
from app.mcp.servers.database_server import database_mcp
from app.mcp.servers.research_server import research_mcp

logger = logging.getLogger("agentx.mcp.clients")


class MCPClientError(Exception):
    """Raised when an MCP client fails to execute or locate a tool."""
    pass


class MCPClient:
    """
    Central client gateway to coordinate and execute tools across
    the independent Research, Database, and Analysis MCP servers.
    """

    def __init__(self) -> None:
        self._servers: Dict[str, FastMCP] = {
            "research": research_mcp,
            "database": database_mcp,
            "analysis": analysis_mcp,
        }
        # Reverse lookup mapping tool name -> server name
        self._tool_to_server_map: Dict[str, str] = {}

    def get_server(self, server_name: str) -> FastMCP:
        """Retrieve server instance by canonical name."""
        key = server_name.lower().strip()
        if key not in self._servers:
            raise MCPClientError(
                f"Unknown MCP server '{server_name}'. Available: {list(self._servers.keys())}"
            )
        return self._servers[key]

    async def list_tools(self, server_name: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all registered tools across all servers, or for a specific server.
        Returns a dictionary of server_name -> list of tool metadata.
        """
        servers = (
            {server_name: self.get_server(server_name)}
            if server_name
            else self._servers
        )

        catalog: Dict[str, List[Dict[str, Any]]] = {}

        for s_name, server in servers.items():
            tool_list = await server.list_tools()
            catalog[s_name] = []
            for t in tool_list:
                self._tool_to_server_map[t.name] = s_name
                catalog[s_name].append(
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters if hasattr(t, "parameters") else {},
                        "server": s_name,
                    }
                )

        return catalog

    @traceable(name="MCP Tool Execution", run_type="tool")
    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        server_name: Optional[str] = None,
    ) -> Any:
        """
        Execute an MCP tool on the target server.
        If server_name is omitted, resolves the server automatically from the tool name.
        """
        args = arguments or {}

        # Resolve server name if not explicitly provided
        if not server_name:
            if not self._tool_to_server_map:
                await self.list_tools()

            resolved_server = self._tool_to_server_map.get(tool_name)
            if not resolved_server:
                # Try finding across servers
                for s_name, s_inst in self._servers.items():
                    server_tools = await s_inst.list_tools()
                    if any(t.name == tool_name for t in server_tools):
                        resolved_server = s_name
                        self._tool_to_server_map[tool_name] = s_name
                        break

            if not resolved_server:
                raise MCPClientError(f"Tool '{tool_name}' not found on any registered MCP server.")
            server = self.get_server(resolved_server)
        else:
            server = self.get_server(server_name)

        # Guardrail input validation on tool arguments
        try:
            from app.guardrails.input_validation import SecurityValidationError, validate_mcp_arguments
            args = validate_mcp_arguments(tool_name, args)
        except SecurityValidationError as sec_exc:
            logger.warning("MCP tool validation blocked by guardrails | tool=%s | error=%s", tool_name, sec_exc)
            return {
                "status": "error",
                "tool": tool_name,
                "message": str(sec_exc),
                "error_type": "security_restriction",
            }

        try:
            # FastMCP call_tool returns tuple: (content_list, result_dict)
            raw_result = await server.call_tool(tool_name, args)

            # Extract result content cleanly
            if isinstance(raw_result, tuple):
                # Typically ([TextContent], {'result': ...})
                if len(raw_result) > 1 and isinstance(raw_result[1], dict) and "result" in raw_result[1]:
                    return raw_result[1]["result"]
                content_list = raw_result[0]
                if content_list and hasattr(content_list[0], "text"):
                    text_val = content_list[0].text
                    try:
                        return json.loads(text_val)
                    except Exception:
                        return text_val
            return raw_result

        except Exception as exc:
            logger.error("MCP tool execution failed | tool=%s | error=%s", tool_name, exc)
            return {
                "status": "error",
                "tool": tool_name,
                "message": f"Execution failed: {str(exc)}",
            }

    async def get_langchain_tools(
        self,
        server_names: Optional[List[str]] = None,
    ) -> List[StructuredTool]:
        """
        Expose MCP tools as LangChain StructuredTool instances
        ready for direct binding into LangGraph agents.
        Preserves the full parameter signature and type schema.
        """
        target_servers = server_names or list(self._servers.keys())
        lc_tools: List[StructuredTool] = []

        for s_name in target_servers:
            server = self.get_server(s_name)
            mcp_tools = await server.list_tools()

            for t in mcp_tools:
                tool_name = t.name
                tool_desc = t.description or f"MCP tool '{tool_name}' from server '{s_name}'"

                # Retrieve the underlying function from the tool manager to retain signature
                tool_obj = server._tool_manager.get_tool(tool_name)
                fn = tool_obj.fn if tool_obj and hasattr(tool_obj, "fn") else None

                if fn is not None:
                    if asyncio.iscoroutinefunction(fn):
                        lc_tool = StructuredTool.from_function(
                            coroutine=fn,
                            name=tool_name,
                            description=tool_desc,
                        )
                    else:
                        lc_tool = StructuredTool.from_function(
                            func=fn,
                            name=tool_name,
                            description=tool_desc,
                        )
                else:
                    # Fallback dynamic runner
                    def _create_runner(t_name: str, server_key: str) -> Callable[..., Any]:
                        async def _run(**kwargs: Any) -> Any:
                            return await self.call_tool(
                                tool_name=t_name,
                                arguments=kwargs,
                                server_name=server_key,
                            )
                        return _run

                    lc_tool = StructuredTool.from_function(
                        coroutine=_create_runner(tool_name, s_name),
                        name=tool_name,
                        description=tool_desc,
                    )

                lc_tools.append(lc_tool)

        return lc_tools


# ------------------------------------------------------------------------------
# Singleton Access
# ------------------------------------------------------------------------------
_global_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """Return shared MCPClient instance."""
    global _global_mcp_client
    if _global_mcp_client is None:
        _global_mcp_client = MCPClient()
    return _global_mcp_client


async def get_langchain_tools(server_names: Optional[List[str]] = None) -> List[StructuredTool]:
    """Helper function to directly retrieve LangChain tools for agent graphs."""
    client = get_mcp_client()
    return await client.get_langchain_tools(server_names)
