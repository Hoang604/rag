"""Type stubs for third-party datasets package."""

def load_dataset(
    path: str,
    name: str | None = None,
    split: str | None = None,
    **kwargs: object,
) -> object: ...
