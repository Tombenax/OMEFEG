import json
import socket
from typing import Any


class UDPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 44699):
        self.host = host
        self.port = port

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.host, self.port))
        self.socket.settimeout(1.0)

        self.running = False

    def start(self):
        self.running = True

        print(f"UDP server listening on {self.host}:{self.port}")

        while self.running:
            try:
                data, address = self.socket.recvfrom(65535)

                message = json.loads(data.decode("utf-8"))

                response = self.handle_message(message, address)

                if response is not None:
                    self.send(response, address)

            except socket.timeout:
                # Give subclasses a chance to check things such as
                # disconnected/timed-out clients.
                self.tick()

            except json.JSONDecodeError:
                print("Received invalid JSON")

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
        data = json.dumps(message).encode("utf-8")
        self.socket.sendto(data, address)

    def stop(self):
        self.running = False
        self.socket.close()
