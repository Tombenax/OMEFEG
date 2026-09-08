import threading
import time

from server import UDPServer

blocks_updates_id = 0

class Player:
    def __init__(self, username, id, address):
        self.coords = [0, 2, 0]
        self.yaw, self.pitch = 0, 0
        self.username = username
        self.id = id
        self.address = address
        self.last_seen = time.time()
        self.last_block_update_seen = 0

    def get_data(self):
        return {
            "position": self.coords,
            "pitch": self.pitch,
            "yaw": self.yaw,
            "username": self.username,
            "id": self.id
        }


players:dict[int:Player] = {}

MAXPLAYERS = 10

IDS = set(range(MAXPLAYERS))

lock = threading.Lock()

# How long a client can go without sending a packet
# before it is considered disconnected.
CLIENT_TIMEOUT = 10

block_updates = {}

class OMEFEGServer(UDPServer):

    def remove_player(self, player_id):
        """Remove a player and return their ID to the available IDs."""
        player = players.pop(player_id, None)

        if player is None:
            return

        IDS.add(player_id)

        print(f"Player {player.username} disconnected. ID {player_id} returned.")

    def check_timeouts(self):
        now = time.time()

        for player_id, player in list(players.items()):
            if now - player.last_seen >= CLIENT_TIMEOUT:
                self.remove_player(player_id)

    def tick(self):
        self.check_timeouts()

    def handle_message(self, message, address):
        global blocks_updates_id, block_updates
        # Check for timed-out players whenever a packet arrives too.
        self.check_timeouts()

        ready_message = {
            "ok": True
        }

        if message.get("connect"):
            if not IDS:
                return {
                    "ok": False,
                    "error": "Server is full",
                }

            # If this address is already connected, don't give it
            # another ID.
            for player in players.values():
                if player.address == address:
                    player.last_seen = time.time()

                    return {
                        "ok": True,
                        "id": player.id,
                    }

            player_id = IDS.pop()

            players[player_id] = Player(
                message["username"],
                player_id,
                address
            )

            print(f"Player {message['username']} connected with ID {player_id}")

            ready_message["id"] = player_id

            return ready_message

        if message.get("disconnect"):
            player_id = message.get("id")

            player = players.get(player_id)

            # Make sure the player owns this ID/address.
            if player is not None and player.address == address:
                self.remove_player(player_id)

            return ready_message

        if message.get("setData"):
            player = players.get(message["id"])

            if player is None:
                return {
                    "ok": False,
                    "error": "Invalid player ID",
                }

            # Prevent another client from pretending to be this player.
            if player.address != address:
                return {
                    "ok": False,
                    "error": "Invalid player address",
                }

            player.last_seen = time.time()

            player.coords = message["coords"]
            player.yaw = message["yaw"]
            player.pitch = message["pitch"]

            return ready_message

        if message.get("getData"):
            player_id = message.get("id")

            # Refresh timeout for the client requesting data.
            if player_id in players:
                player = players[player_id]

                if player.address == address:
                    player.last_seen = time.time()

            ready_message["players"] = []

            for player in players.values():
                ready_message["players"].append(player.get_data())

            return ready_message

        if message.get("getBlockData"):
            player_id = message["id"]

            ready_message["block_updates"] = []

            pv = len(block_updates)

            for update_idx in range(players[player_id].last_block_update_seen, pv):
                block_update = block_updates[update_idx]
                ready_message["block_updates"].append(block_update)

            players[player_id].last_block_update_seen = pv

            return ready_message

        if message.get("setBlockData"):
            if message["block update"]:
                with lock:
                        for bu in message["block update"]:
                            block_updates[blocks_updates_id] = bu

                            blocks_updates_id += 1

            return ready_message



        return {
            "ok": False,
            "error": "Unknown message type",
        }


if __name__ == "__main__":
    server = OMEFEGServer(port=44699)

    try:
        server.start()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.stop()
