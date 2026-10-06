from __future__ import annotations

from mcp.shared.exceptions import MCPError

# Standard JSON-RPC 2.0 error codes
E_INVALID_PARAMS: int = -32602
E_INTERNAL_ERROR: int = -32603

E_AST_GROUNDING_VALIDATION: int = E_INVALID_PARAMS
E_INVALID_DOCUMENT_HIERARCHY: int = E_INVALID_PARAMS
E_STORAGE_CONNECTION: int = E_INTERNAL_ERROR
E_CORPUS_INTEGRITY_VIOLATION: int = E_INTERNAL_ERROR
E_VECTOR_DIMENSION_MISMATCH: int = E_INTERNAL_ERROR


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
