import json
import socket
import time
import traceback
from typing import Any


class UDPServer:
    # Short recv timeout so tick() runs frequently even under load.
    # handle_message is also throttled separately (see OMEFEGServer).
    TICK_INTERVAL = 0.2
    RECV_BYTES = 65535

    def __init__(self, host: str = "0.0.0.0", port: int = 44699):
        self.host = host
        self.port = port

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Larger buffers so packet bursts (many clients polling) don't
        # get dropped by the OS before we can drain them.
        try:
            self.socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024
            )
            self.socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024
            )
        except OSError:
            pass
        self.socket.bind((self.host, self.port))
        self.socket.settimeout(self.TICK_INTERVAL)

        self.running = False
        self._last_tick = 0.0

    def start(self):
        self.running = True

        print(f"UDP server listening on {self.host}:{self.port}")

        while self.running:
            try:
                data, address = self.socket.recvfrom(self.RECV_BYTES)

                try:
                    message = json.loads(data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    print(f"Received invalid JSON from {address}")
                    continue

                try:
                    response = self.handle_message(message, address)
                except Exception:
                    # Never let one bad packet kill the server loop.
                    print(f"Error handling message from {address}:")
                    traceback.print_exc()
                    try:
                        self.send(
                            {"ok": False, "error": "internal error"},
                            address,
                        )
                    except OSError:
                        pass
                    continue

                if response is not None:
                    try:
                        self.send(response, address)
                    except OSError:
                        pass

                # tick() must also run when traffic is heavy, otherwise
                # timeout checks starve (old code only ticked on timeout).
                now = time.time()
                if now - self._last_tick >= 1.0:
                    self._last_tick = now
                    try:
                        self.tick()
                    except Exception:
                        traceback.print_exc()

            except socket.timeout:
                # Give subclasses a chance to check things such as
                # disconnected/timed-out clients.
                self._last_tick = time.time()
                try:
                    self.tick()
                except Exception:
                    traceback.print_exc()

            except OSError:
                break

    def handle_message(self, message: dict[str, Any], address):
        return {
            "ok": True,
            "message": "Hello from the UDP server!",
        }

    def tick(self):
        """
        Called periodically when the server isn't receiving packets.
        Subclasses can override this.
        """
        pass

    def send(self, message: dict[str, Any], address):
        # Compact separators shrink every packet (fewer bytes on the wire).
        data = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self.socket.sendto(data, address)

    def stop(self):
        self.running = False
        self.socket.close()
