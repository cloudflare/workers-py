from dataclasses import dataclass
from typing import Any, Literal, get_args

EncodeBody = Literal["automatic", "manual"]


@dataclass(frozen=True, kw_only=True)
class BaseOptions:
    """Options shared by the ASGI and WSGI adapters.

    Downstream adapters should inherit from this class to define their own options.
    """

    # Whether to encode the body according to the ``Content-Encoding`` header
    # See https://developers.cloudflare.com/workers/runtime-apis/response/#the-encodebody-option
    encode_body: EncodeBody = "automatic"

    def __post_init__(self) -> None:
        if self.encode_body not in get_args(EncodeBody):
            raise ValueError(
                f"encode_body must be one of {get_args(EncodeBody)}, "
                f"got {self.encode_body!r}"
            )

    def response_init(self) -> dict[str, Any]:
        """Extra keyword arguments for ``Response.new``."""
        init: dict[str, Any] = {}
        if self.encode_body != "automatic":
            init["encodeBody"] = self.encode_body
        return init
