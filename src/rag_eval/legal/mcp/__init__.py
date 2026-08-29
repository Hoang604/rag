"""Model Context Protocol (MCP) JSON-RPC 2.0 Server and Specialized Tool Ecosystem."""

from rag_eval.legal.mcp.server import LegalMCPServer, run_mcp_server
from rag_eval.legal.mcp.tools import LegalMCPTools

__all__ = ["LegalMCPServer", "LegalMCPTools", "run_mcp_server"]
