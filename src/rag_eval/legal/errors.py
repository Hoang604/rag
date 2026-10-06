from __future__ import annotations

from mcp.shared.exceptions import MCPError

E_AST_GROUNDING_VALIDATION: int = -32001
E_STORAGE_CONNECTION: int = -32002
E_INVALID_DOCUMENT_HIERARCHY: int = -32003
E_CORPUS_INTEGRITY_VIOLATION: int = -32004
E_VECTOR_DIMENSION_MISMATCH: int = -32005


class LegalDomainError(MCPError):
    """Domain-specific exception conforming to JSON-RPC 2.0 error specification and MCPError."""

    def __init__(
        self,
        error_code: int,
        message: str,
        data: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code=error_code, message=message, data=data)
        self.error_code = error_code
