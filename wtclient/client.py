import asyncio
import os
from aioquic.asyncio.client import connect
from aioquic.h3.connection import H3_ALPN
from aioquic.quic.configuration import QuicConfiguration


async def main():
    server_host = os.getenv("SERVER_HOST", "127.0.0.1")
    server_port = 4433
    server_endpoint = f"https://{server_host}:{server_port}/webtransport"
    configuration = QuicConfiguration(
        alpn_protocols=H3_ALPN,
        is_client=True,
        max_datagram_frame_size=65536,
    )
    configuration.load_verify_locations("pycacert.pem")
    async with connect(
        host=server_host,
        port=server_port,
        configuration=configuration,
    ) as quic_protocol:
        reader, writer = await quic_protocol.create_stream()
        request_bytes = b"PING"
        writer.write(request_bytes)
        print(f"{request_bytes.decode()} :->")
        response = await reader.read(4)
        print(f"     <-: {response.decode()}")


if __name__ == "__main__":
    asyncio.run(main())
