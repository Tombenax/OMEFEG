import json
import socket
from typing import Any


class Network:
    # Match the server default (server/main.py serves 44699).
    # Old default 9999 never matched, forcing every user to pass the port.
    # Shorter timeout: a tick runs at 20Hz, so waiting 5s on a lost UDP
    # packet stalls the net thread for seconds. Callers treat timeout as
    # "packet lost, try next tick" instead of blocking.
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 44699,
        timeout: float = 2.0,
    ):
        self.address = (host, port)
        self.timeout = timeout

        self.socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )
        try:
            self.socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024
            )
            self.socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024
            )
        except OSError:
            pass

        self.socket.settimeout(timeout)
        self._closed = False

        # Retry connect a few times: UDP has no handshake, one dropped
        # packet used to mean "game never starts".
        last_error = None
        for _ in range(3):
            try:
                self.send({
                    "connect": True,
                    "username": "NOONE"
                })
                data = self.receive()
                break
            except (socket.timeout, OSError) as e:
                last_error = e
                continue
        else:
            raise ConnectionError(
                f"Could not connect to {self.address}: {last_error}"
            )

        if not data.get("ok", False):
            raise ConnectionError(f"Server refused connection: {data}")

        self.id = data["id"]
        # Per-connection secret (see server/main.py). Identifies us even
        # when a tunnel/NAT shares or rebinds our source address. Old
        # servers don't send one; tag() then just sends the id.
        self.token = data.get("token")

    def send(self, message: dict[str, Any]):
        # Compact separators: less bytes per packet.
        data = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self.socket.sendto(data, self.address)

    def receive(self) -> dict[str, Any]:
        data, _ = self.socket.recvfrom(65535)

        return json.loads(data.decode("utf-8"))

    def tag(self, message: dict[str, Any]) -> dict[str, Any]:
        """Stamp a message with our id + token (mutates and returns it)."""
        message["id"] = self.id
        if self.token is not None:
            message["token"] = self.token
        return message

    def request(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        Send a message and wait for a response.
        May raise socket.timeout on packet loss; callers should treat
        that as lost-packet, not fatal.
        """
        self.send(message)
        return self.receive()

    def tick(
        self,
        player_id: int,
        coords,
        yaw,
        pitch,
        block_updates: list,
    ) -> dict[str, Any] | None:
        """Combined 1-RTT update (replaces 4x setData/getData/setBlock/getBlock).

        Returns None on timeout (packet loss) so the caller can just try
        again next tick. Returns the dict on rate_limited too so the
        caller can back off.
        """
        try:
            # Round here as well so we don't send full float precision.
            qcoords = [round(float(c), 3) for c in coords]
        except (TypeError, ValueError):
            qcoords = coords
        msg: dict[str, Any] = {
            "tick": True,
            "id": player_id,
            "coords": qcoords,
            "yaw": round(float(yaw), 2),
            "pitch": round(float(pitch), 2),
            "block update": block_updates,
        }
        if self.token is not None:
            msg["token"] = self.token
        try:
            return self.request(msg)
        except socket.timeout:
            return None

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.socket.close()
        except OSError:
            pass
