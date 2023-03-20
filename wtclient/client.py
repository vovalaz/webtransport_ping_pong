import os
from aioquic.asyncio.client import connect
from aioquic.quic.configuration import QuicConfiguration


async def main():
    server_host = os.getenv("SERVER_HOST", "127.0.0.1")
    server_port = 4433
    server_endpoint = f"https://{server_host}:{server_port}/webtransport"
    configuration = QuicConfiguration(alpn_protocols=["h3"])
    configuration.load_verify_locations("pycacert.pem")
    async with connect(
        host=server_host,
        port=server_port,
        configuration=configuration,
    ) as quic_protocol:
        reader, writer = await quic_protocol.create_stream()
        
