import asyncio
import logging
from typing import Optional

from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.h3.events import H3Event, HeadersReceived, WebTransportStreamDataReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, ProtocolNegotiated
from aioquic.h3.connection import H3_ALPN, H3Connection


logger = logging.getLogger(__name__)


class ServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._http: Optional[H3Connection] = None

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, ProtocolNegotiated):
            self._http = H3Connection(self._quic, enable_webtransport=True)

        if self._http is not None:
            for h3_event in self._http.handle_event(event):
                self.handle_h3_event(h3_event)

    def handle_h3_event(self, event: H3Event):
        if isinstance(event, HeadersReceived):  # perform webtransport handshake
            headers = {header: value for header, value in event.headers}
            if headers.get(b":method") == b"CONNECT" and headers.get(b":protocol") == b"webtransport":
                path = headers.get(b":path")
                authority = headers.get(b":authority")
                if all([path, authority]) and path == b"/webtransport":
                    self._send_response_headers(event.stream_id, 200)
                else:
                    self._send_response_headers(event.stream_id, 400, end_stream=True)
        elif isinstance(event, WebTransportStreamDataReceived):  # handle received the PING message
            if event.data == b"PING":
                response = b"PONG"
                print(f"Stream: {event.stream_id} Received: {event.data.decode()}")
                self._send_webtransport_data(event.stream_id, response, end_stream=False)
                print(f"Stream: {event.stream_id} Sent: {response.decode()}")

    def _send_response_headers(self, stream_id, status_code, end_stream=False):
        headers = [(b":status", str(status_code).encode())]
        if status_code == 200:
            headers.append((b"sec-webtransport-http3-draft", b"draft02"))
        self._http.send_headers(stream_id=stream_id, headers=headers, end_stream=end_stream)

    def _send_webtransport_data(self, stream_id, data, end_stream=False):
        if self._http is not None:
            self._quic.send_stream_data(stream_id, data, end_stream)


if __name__ == "__main__":
    BIND_ADDRESS, BIND_PORT = "0.0.0.0", 4433

    configuration = QuicConfiguration(
        alpn_protocols=H3_ALPN,
        is_client=False,
        max_datagram_frame_size=65536,
    )
    configuration.load_cert_chain("ssl_cert.pem", "ssl_key.pem")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        serve(
            BIND_ADDRESS,
            BIND_PORT,
            configuration=configuration,
            create_protocol=ServerProtocol,
            retry=True,
        )
    )
    print("Listening on https://{}:{}".format(BIND_ADDRESS, BIND_PORT))
    loop.run_forever()
