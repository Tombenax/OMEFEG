import json
import socket
from typing import Any


class Network:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9999,
        timeout: float = 5.0,
    ):
        self.address = (host, port)

        self.socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        self.socket.settimeout(timeout)

        self.send({
            "connect": True,
            "username": "NOONE"
        })

        data = self.receive()

        self.id = data["id"]

    def send(self, message: dict[str, Any]):
        data = json.dumps(message).encode("utf-8")
        self.socket.sendto(data, self.address)

    def receive(self) -> dict[str, Any]:
        data, _ = self.socket.recvfrom(65535)

        return json.loads(data.decode("utf-8"))

    def request(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        Send a message and wait for a response.
        """
        self.send(message)
        return self.receive()

    def close(self):
        self.socket.close()
