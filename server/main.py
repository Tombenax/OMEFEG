import collections
import secrets
import threading
import time

from server import UDPServer


class Player:
    def __init__(self, username, id, address):
        self.coords = [0, 2, 0]
        self.yaw, self.pitch = 0, 0
        self.username = username
        self.id = id
        self.address = address
        # Secret per-connection token. UDP has no handshake, and tunnels /
        # NATs (e.g. playit.gg) can share or rebind source addresses, so
        # (id, address) is NOT a reliable identity: two players behind one
        # address used to be merged into one ID, and a port rebind made
        # every tick fail validation (remote avatar frozen at spawn).
        # The token identifies the connection; the address is just adopted
        # on each valid packet.
        self.token = secrets.token_hex(8)
        self.last_seen = time.time()
        # Start at the current history head so a fresh join doesn't get
        # sent the entire server history on its first getBlockData.
        # Overwritten with the real head in handle_message("connect").
        self.last_block_update_seen = 0

    def get_data(self):
        # Round floats: smaller JSON, same visual result.
        try:
            pos = [round(float(c), 3) for c in self.coords]
        except (TypeError, ValueError):
            pos = self.coords
        try:
            yaw = round(float(self.yaw), 2)
        except (TypeError, ValueError):
            yaw = self.yaw
        try:
            pitch = round(float(self.pitch), 2)
        except (TypeError, ValueError):
            pitch = self.pitch
        return {
            "position": pos,
            "pitch": pitch,
            "yaw": yaw,
            "username": self.username,
            "id": self.id
        }


players: dict[int, Player] = {}

MAXPLAYERS = 10

IDS = set(range(MAXPLAYERS))

lock = threading.Lock()

# How long a client can go without sending a packet
# before it is considered disconnected.
CLIENT_TIMEOUT = 10

# --- Bounded block history (fixes unbounded-memory + O(n) fetch) ---
# Old code: block_updates = {} growing forever, every getBlockData scanned
# from last_seen..len() and sent it all in one UDP datagram.
BLOCK_HISTORY_LIMIT = 2000
# Max updates returned per response: keeps datagrams MTU-safe-ish and
# paginates via has_more/next_seen instead of one giant burst.
MAX_UPDATES_PER_RESPONSE = 200
# Max updates accepted per incoming packet: bounds a malicious/flooding client.
MAX_BLOCK_UPDATE_BATCH = 200

# deque holds block updates in order; blocks_updates_id is the monotonic
# id that *would* be assigned to the next append. History base id is
# blocks_updates_id - len(block_updates).
block_updates: collections.deque = collections.deque(maxlen=BLOCK_HISTORY_LIMIT)
blocks_updates_id = 0

# Authoritative edit overlay: voxel -> block name, or None when destroyed.
# Deltas only reach players who are online; a late joiner starts its cursor
# at the current head and would miss every earlier edit, so it instead
# pulls this overlay once via getSnapshot (same entry shapes as deltas).
world_overlay: dict[tuple, str | None] = {}

# Snapshot page size (same MTU rationale as delta pages).
SNAPSHOT_PAGE = 200

# --- Per-address rate limiting (fixes client busy-loop flooding) ---
# Sliding 1s window; sustained spam above this gets a rate_limited reply
# instead of full processing. 20Hz single-tick clients use ~20 pps, well
# under the limit; old 4-packets-per-frame busy loops exceed it.
RATE_WINDOW = 1.0
MAX_PPS = 50


def _history_base_locked():
    return blocks_updates_id - len(block_updates)


class OMEFEGServer(UDPServer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_timeout_check = 0.0
        # address -> deque[timestamps]
        self._pps: dict = {}
        self._pps_lock = threading.Lock()

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

    def _throttled_timeout_check(self):
        # Old code scanned all players on EVERY packet. Throttle to 1Hz.
        now = time.time()
        if now - self._last_timeout_check >= 1.0:
            self._last_timeout_check = now
            self.check_timeouts()

    def tick(self):
        self._last_timeout_check = time.time()
        self.check_timeouts()
        # Opportunistically drop empty rate-limit entries.
        now = time.time()
        with self._pps_lock:
            for addr in list(self._pps.keys()):
                dq = self._pps[addr]
                while dq and now - dq[0] > RATE_WINDOW:
                    dq.popleft()
                if not dq:
                    del self._pps[addr]

    def _is_rate_limited(self, address):
        now = time.time()
        with self._pps_lock:
            dq = self._pps.get(address)
            if dq is None:
                dq = collections.deque()
                self._pps[address] = dq
            while dq and now - dq[0] > RATE_WINDOW:
                dq.popleft()
            dq.append(now)
            return len(dq) > MAX_PPS

    def _validate_player(self, message, address):
        """Return (player, error_response). error_response is None on success.

        Token auth: a matching (id, token) wins and adopts the sender's
        current address (survives NAT/tunnel port rebinds). Messages from
        old clients without a token fall back to the legacy address check.
        """
        player_id = message.get("id")
        if player_id is None:
            return None, {"ok": False, "error": "Missing player ID"}
        player = players.get(player_id)
        if player is None:
            return None, {"ok": False, "error": "Invalid player ID"}
        token = message.get("token")
        if token is not None:
            if token != player.token:
                return None, {"ok": False, "error": "Invalid token"}
            if player.address != address:
                player.address = address
            return player, None
        if player.address != address:
            return None, {"ok": False, "error": "Invalid player address"}
        return player, None

    def _append_block_updates(self, updates):
        """Append incoming block updates, capped. Returns count appended."""
        global blocks_updates_id, world_overlay
        if not updates:
            return 0
        if not isinstance(updates, list):
            return 0
        # Cap a single packet's contribution.
        updates = updates[:MAX_BLOCK_UPDATE_BATCH]
        with lock:
            for bu in updates:
                # Basic shape check so one malformed entry can't poison history.
                if not isinstance(bu, (list, tuple)) or len(bu) not in (2, 3):
                    continue
                block_updates.append(bu)
                blocks_updates_id += 1
                # Maintain the overlay for late joiners: place records the
                # block name, destroy records a tombstone (the voxel may be
                # worldgen rock the joiner would otherwise generate).
                try:
                    if len(bu) == 2:
                        world_overlay[tuple(bu[1])] = bu[0]
                    else:
                        world_overlay[(bu[0], bu[1], bu[2])] = None
                except (TypeError, IndexError):
                    continue
        return len(updates)

    def _get_snapshot_page(self, offset):
        """One page of the overlay in delta shapes (place=[name,pos],
        gone=[x,y,z]), sorted for stable pagination."""
        with lock:
            items = sorted(world_overlay.items())
            total = len(items)
            offset = max(0, min(offset, total))
            page = []
            for pos, name in items[offset:offset + SNAPSHOT_PAGE]:
                if name is None:
                    page.append([pos[0], pos[1], pos[2]])
                else:
                    page.append([name, [pos[0], pos[1], pos[2]]])
            next_offset = offset + len(page)
            return page, next_offset, next_offset >= total

    def _get_block_page(self, player):
        """Paginated read of history for player. Updates its cursor.

        Returns (updates_list, next_seen, has_more, resync).
        """
        global blocks_updates_id
        with lock:
            head = blocks_updates_id
            base = head - len(block_updates)
            last_seen = player.last_block_update_seen
            resync = False
            if last_seen < base:
                # History already evicted what this client missed.
                resync = True
                last_seen = base
            if last_seen > head:
                last_seen = head
            start_idx = last_seen - base  # index into deque
            page = list(block_updates)[start_idx:start_idx + MAX_UPDATES_PER_RESPONSE]
            next_seen = last_seen + len(page)
            has_more = next_seen < head
            player.last_block_update_seen = next_seen
            return page, next_seen, has_more, resync

    def _players_snapshot(self):
        return [p.get_data() for p in players.values()]

    def _handle_tick(self, message, address):
        """Combined 1-RTT update: replaces setData+getData+setBlock+getBlock."""
        player, err = self._validate_player(message, address)
        if err is not None:
            return err
        # Position update (tolerate missing keys from old clients).
        if "coords" in message:
            player.coords = message["coords"]
        if "yaw" in message:
            player.yaw = message["yaw"]
        if "pitch" in message:
            player.pitch = message["pitch"]
        player.last_seen = time.time()
        # Block updates may use either the old "block update" key or
        # the alias "block_update".
        incoming = message.get("block update", message.get("block_update", []))
        if incoming:
            self._append_block_updates(incoming)
        page, next_seen, has_more, resync = self._get_block_page(player)
        return {
            "ok": True,
            "players": self._players_snapshot(),
            "block_updates": page,
            "next_seen": next_seen,
            "has_more": has_more,
            "resync": resync,
        }

    def handle_message(self, message, address):
        global blocks_updates_id, block_updates
        try:
            # Throttled (1Hz) instead of per-packet full scan.
            self._throttled_timeout_check()

            if not isinstance(message, dict):
                return {"ok": False, "error": "Invalid message"}

            # Rate-limit high-frequency gameplay packets, never connect/disconnect.
            if not message.get("connect") and not message.get("disconnect"):
                if self._is_rate_limited(address):
                    return {"ok": False, "error": "rate_limited", "retry": True}

            ready_message = {
                "ok": True
            }

            if message.get("connect"):
                # Reconnect with a known (id, token): resume that player
                # (and adopt the current address) instead of leaking an ID.
                if message.get("id") is not None and message.get("token"):
                    player = players.get(message.get("id"))
                    if player is not None and player.token == message.get("token"):
                        player.address = address
                        player.last_seen = time.time()
                        return {"ok": True, "id": player.id, "token": player.token}

                if not IDS:
                    return {
                        "ok": False,
                        "error": "Server is full",
                    }

                # NOTE: no address-based dedup here on purpose. Two game
                # instances behind one tunnel/NAT address are different
                # players; merging them gave both the same ID, so each
                # client filtered "itself" out and nobody saw anyone move.
                player_id = IDS.pop()

                username = message.get("username", "UNKNOWN")

                new_player = Player(
                    username,
                    player_id,
                    address
                )
                # Don't flood joiners with full history.
                new_player.last_block_update_seen = blocks_updates_id
                players[player_id] = new_player

                print(f"Player {username} connected with ID {player_id}")

                ready_message["id"] = player_id
                ready_message["token"] = new_player.token

                return ready_message

            if message.get("disconnect"):
                player_id = message.get("id")

                player = players.get(player_id)

                # Token wins; legacy clients fall back to address match.
                if player is not None:
                    token = message.get("token")
                    if token is not None:
                        if token == player.token:
                            self.remove_player(player_id)
                    elif player.address == address:
                        self.remove_player(player_id)

                return ready_message

            # New combined path: 1 RTT instead of 4.
            if message.get("tick"):
                return self._handle_tick(message, address)

            if message.get("setData"):
                player, err = self._validate_player(message, address)
                if err is not None:
                    return err

                player.last_seen = time.time()

                if "coords" in message:
                    player.coords = message["coords"]
                if "yaw" in message:
                    player.yaw = message["yaw"]
                if "pitch" in message:
                    player.pitch = message["pitch"]

                return ready_message

            if message.get("getData"):
                player_id = message.get("id")

                # Refresh timeout for the client requesting data.
                if player_id in players:
                    player = players[player_id]
                    token = message.get("token")

                    if token is not None:
                        if token == player.token:
                            player.address = address
                            player.last_seen = time.time()
                    elif player.address == address:
                        player.last_seen = time.time()

                ready_message["players"] = self._players_snapshot()

                return ready_message

            if message.get("getBlockData"):
                player, err = self._validate_player(message, address)
                if err is not None:
                    return err

                player.last_seen = time.time()
                page, next_seen, has_more, resync = self._get_block_page(player)

                ready_message["block_updates"] = page
                ready_message["next_seen"] = next_seen
                ready_message["has_more"] = has_more
                ready_message["resync"] = resync

                return ready_message

            if message.get("getSnapshot"):
                player, err = self._validate_player(message, address)
                if err is not None:
                    return err

                player.last_seen = time.time()
                try:
                    offset = int(message.get("offset", 0))
                except (TypeError, ValueError):
                    offset = 0
                page, next_offset, done = self._get_snapshot_page(offset)

                ready_message["block_updates"] = page
                ready_message["next_offset"] = next_offset
                ready_message["done"] = done

                return ready_message

            if message.get("setBlockData"):
                # Old clients send no id here; new tick path validates.
                # Accept anonymous for back-compat but still rate-limited
                # (see top) and batch-capped.
                player_id = message.get("id")
                if player_id is not None:
                    player, err = self._validate_player(message, address)
                    if err is not None:
                        return err
                    player.last_seen = time.time()
                incoming = message.get("block update", message.get("block_update", []))
                if incoming:
                    self._append_block_updates(incoming)

                return ready_message

            return {
                "ok": False,
                "error": "Unknown message type",
            }
        except Exception as e:
            print(f"handle_message error: {e}")
            return {"ok": False, "error": "internal error"}


if __name__ == "__main__":
    server = OMEFEGServer(port=44699)

    try:
        server.start()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.stop()
