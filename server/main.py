import socket
import threading
import json

PORT = 5050
SERVER = socket.gethostbyname(socket.gethostname())
ADDR = (SERVER, PORT)

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)

all_players = []

MAXPLAYERS = 20

IDS = set(i for i in range(MAXPLAYERS))

destroyed_blocks = []
placed_blocks = []

chat_owners = []
chat_messages = []

class Player:
    def __init__(self, pos, name, yaw, pitch, id):
        self.pos = pos
        self.name = name
        self.yaw = yaw
        self.pitch = pitch
        self.id = id
    
    def data(self):
        return json.dumps({
            "pos": self.pos,
            "name": self.name,
            "yaw": self.yaw,
            "pitch": self.pitch,
            "id": self.id
        })

def log(message, status):
    print(f"[{status}]: {message}")

def handle_client(conn, addr):
    log(f"New connection from {addr}", "INFO")

    myID = IDS.pop()

    conn.send(str(myID).encode("utf-8"))

    msg = json.loads(conn.recv(2048).decode('utf-8'))

    position = len(all_players)
    all_players.append(Player([msg["x"], msg["y"], msg["z"]], msg["name"], 0, 0, myID))

    conn.send("recived".encode("utf-8"))

    connected = True
    while connected:
        try:
            msg = conn.recv(2048).decode('utf-8')
            if msg:
                if msg == "gimmietheDATA":
                    prepared_list = [[], [chat_owners, chat_messages], placed_blocks, destroyed_blocks]
                    for player in all_players:
                        if not player.id == myID:
                            prepared_list[0].append(player.data())
                    conn.send(json.dumps(prepared_list).encode('utf-8'))

                    data = json.loads(conn.recv(2048).decode('utf-8'))
                    all_players[position].pos = data["position"]
                    all_players[position].yaw = data["orientation"][0]
                    all_players[position].pitch = data["orientation"][1]
                    all_players[position].name = data["username"]
                    placed_blocks.extend(data["blocks placed at"])
                    destroyed_blocks.extend(data["blocks broken at"])
                    if data["chat message"] != "":
                        chat_messages.append(data["chat message"])
                        chat_owners.append(data["username"])
                        
                        if len(chat_messages) > 10:
                            chat_messages.pop(0)
                            chat_owners.pop(0)
                        
                        log(f"|{data['username']}|:{data['chat message']}", "CHAT:")
                    conn.send("recived".encode("utf-8"))

            else:
                connected = False

        except ConnectionResetError:
            connected = False

    log(f"Disconnection from {addr}", "INFO")
    all_players.pop(position)
    IDS.add(myID)
    conn.close()

log(f"Server is listening on {SERVER}:{PORT}", "INFO")
log("Press 'Ctrl + C' to quit", "COMMANDS")

while True:
    try:
        server.listen()
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()
    except KeyboardInterrupt:
        log("turning OFF the server", "INFO")
