from .websocket import AMBWebsocketProvider, handle_create_protocol

async_provider = AMBWebsocketProvider(
    endpoint_uri=config.env('AMB_WS_ENDPOINT'),
    websocket_kwargs=dict(
        create_protocol=handle_create_protocol
    )
)
async_w3 = Web3(async_provider)
import collections.abc
import websockets
from websockets.handshake import build_request
from websockets.http import Headers
from .signer import aws_auth
from typing import (Optional, Sequence, Any)
from requests.models import PreparedRequest
from requests import Request
from web3.providers import WebsocketProvider
from base64 import b64encode, b64decode
import asyncio
from web3.types import (
    RPCEndpoint,
    RPCResponse,
)


class AMBWebsocketProvider(WebsocketProvider):
    def encode_rpc_request(self, method: RPCEndpoint, params: Any):
        as_bytes = super().encode_rpc_request(method, params)
        return as_bytes.decode()

    # typing: ignore
    def decode_rpc_response(self, raw_response: str):  # typing: ignore
        as_bytes = raw_response.encode()
        return super().decode_rpc_response(as_bytes)


class AMBWebSocketClientProtocol(websockets.client.WebSocketClientProtocol):
    async def handshake(self,
                        wsuri: websockets.WebSocketURI,
                        origin: Optional[websockets.typing.Origin] = None,
                        available_extensions: Optional[Sequence[websockets.extensions.base.ClientExtensionFactory]] = None,
                        available_subprotocols: Optional[Sequence[websockets.typing.Subprotocol]] = None,
                        extra_headers: Optional[websockets.http.HeadersLike] = None):
        """
        Perform the client side of the opening handshake.

        :param origin: sets the Origin HTTP header
        :param available_extensions: list of supported extensions in the order
            in which they should be used
        :param available_subprotocols: list of supported subprotocols in order
            of decreasing preference
        :param extra_headers: sets additional HTTP request headers; it must be
            a :class:`~websockets.http.Headers` instance, a
            :class:`~collections.abc.Mapping`, or an iterable of ``(name,
            value)`` pairs
        :raises ~websockets.exceptions.InvalidHandshake: if the handshake
            fails

        """
        request_headers = Headers()

        if wsuri.port == (443 if wsuri.secure else 80):  # pragma: no cover
            request_headers["Host"] = wsuri.host
        else:
            request_headers["Host"] = f"{wsuri.host}:{wsuri.port}"

        # if wsuri.user_info:
        #     request_headers["Authorization"] = build_authorization_basic(
        #         *wsuri.user_info
        #     )

        if origin is not None:
            request_headers["Origin"] = origin

        key = build_request(request_headers)

        if available_extensions is not None:
            extensions_header = websockets.headers.build_extension(
                [(extension_factory.name,
                  extension_factory.get_request_params())
                 for extension_factory in available_extensions])
            request_headers["Sec-WebSocket-Extensions"] = extensions_header

        if available_subprotocols is not None:
            protocol_header = websockets.headers.build_subprotocol(
                available_subprotocols)
            request_headers["Sec-WebSocket-Protocol"] = protocol_header

        if extra_headers is not None:
            if isinstance(extra_headers, Headers):
                extra_headers = extra_headers.raw_items()
            elif isinstance(extra_headers, collections.abc.Mapping):
                extra_headers = extra_headers.items()
            for name, value in extra_headers:
                request_headers[name] = value

        request_headers.setdefault("User-Agent", websockets.http.USER_AGENT)

        req = Request('GET', f'https://{wsuri.host}/',
                      data='', headers=request_headers)
        prepared_request = req.prepare()
        encrypted_request = aws_auth(prepared_request)
        self.write_http_request(wsuri.resource_name,
                                Headers(encrypted_request.headers))
        status_code, response_headers = await self.read_http_response()
        if status_code in (301, 302, 303, 307, 308):
            if "Location" not in response_headers:
                raise websockets.exceptions.InvalidHeader("Location")
            raise websockets.exceptions.RedirectHandshake(
                response_headers["Location"])
        elif status_code != 101:
            raise websockets.exceptions.InvalidStatusCode(status_code)

        websockets.handshake.check_response(response_headers, key)

        self.extensions = self.process_extensions(
            response_headers, available_extensions
        )

        self.subprotocol = self.process_subprotocol(
            response_headers, available_subprotocols
        )

        self.connection_open()


def handle_create_protocol(*args, **kwargs):
    return AMBWebSocketClientProtocol(*args, **kwargs)
