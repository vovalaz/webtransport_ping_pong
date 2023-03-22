import asyncio
import os
from time import sleep
from collections import deque
from typing import Optional, Dict, Deque
from aioquic.h3.events import H3Event, HeadersReceived, WebTransportStreamDataReceived
from aioquic.quic.events import QuicEvent, ProtocolNegotiated
from aioquic.h3.connection import H3Connection
from aioquic.asyncio import QuicConnectionProtocol, connect
from aioquic.h3.connection import H3_ALPN
from aioquic.quic.configuration import QuicConfiguration


class ClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._http: Optional[H3Connection] = None
        self.pushes: Dict[int, Deque[H3Event]] = {}
        self._request_events: Dict[int, Deque[H3Event]] = {}
        self._request_waiter: Dict[int, asyncio.Future[Deque[H3Event]]] = {}

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, ProtocolNegotiated):
            self._http = H3Connection(self._quic, enable_webtransport=True)

        if self._http is not None:
            for h3_event in self._http.handle_event(event):
                self.handle_h3_event(h3_event)

    def handle_h3_event(self, event: H3Event):
        if isinstance(event, (HeadersReceived, WebTransportStreamDataReceived)):
            stream_id = event.stream_id
            if stream_id in self._request_events:
                self._request_events[event.stream_id].append(event)
                if event.stream_ended:
                    request_waiter = self._request_waiter.pop(stream_id)
                    request_waiter.set_result(self._request_events.pop(stream_id))

    async def request(self, content) -> Deque[H3Event]:
        stream_id = self._quic.get_next_available_stream_id()
        self._http.send_headers(
            stream_id=stream_id,
            headers=[
                (b":method", b"CONNECT"),
                (b":protocol", b"webtransport"),
                (b":path", b"/webtransport"),
                (b":authority", b"zewald"),
            ],
            end_stream=not content,
        )
        if content:
            self._http.send_data(
                stream_id=stream_id, data=content, end_stream=True,
            )

        waiter = self._loop.create_future()
        self._request_events[stream_id] = deque()
        self._request_waiter[stream_id] = waiter
        self.transmit()

        return await asyncio.shield(waiter)


async def perform_ping(client: ClientProtocol):
    data = b"PING"
    http_events = await client.request(data)
    for http_event in http_events:
        if isinstance(http_event, WebTransportStreamDataReceived):
            print(f"Received {http_event.data}")


async def main(server_host, server_port):
    server_endpoint = f"https://{server_host}:{server_port}/webtransport"
    configuration = QuicConfiguration(
        alpn_protocols=H3_ALPN,
        is_client=True,
        max_datagram_frame_size=65536,
    )
    # configuration.load_verify_locations("pycacert.pem")
    async with connect(
        host=server_host,
        port=server_port,
        configuration=configuration,
        create_protocol=ClientProtocol,
    ) as quic_protocol:
        while True:
            await perform_ping(quic_protocol)
            sleep(1)
        # reader, writer = await quic_protocol.create_stream()
        # request_bytes = b"PING"
        # writer.write(request_bytes)
        # print(f"{request_bytes.decode()} :->")
        # response = await reader.read(4)
        # print(f"     <-: {response.decode()}")


if __name__ == "__main__":
    server_host = os.getenv("SERVER_HOST", "127.0.0.1")
    server_port = 4433
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(server_host, server_port))
    print(f"Attempting pings to https://{server_host}:{server_port}")
    loop.run_forever()
