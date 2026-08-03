import socket
import json

class Network:
    def __init__(self, data:dict, server_ip:str, server_port:int):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server = server_ip
        self.port = server_port
        self.addr = (self.server, self.port)
        self.id = self.connect()
        self.send(json.dumps(data), False)
    
    def connect(self):
        try:
            self.client.connect(self.addr)
            return self.client.recv(2048).decode()
        except:
            print("failed to connect!!")
    
    def send(self, data:str, should_return=True, recive_size=2048):
        try:
            self.client.send(str.encode(data))
            return_data = self.client.recv(recive_size).decode()
            if should_return:
                return return_data
        except socket.error as e:
            print(e)

if __name__ == "__main__":
    n = Network({"x":0, "y":0, "z":0, "name":"ServerOwner"})
    print(n.id)
    print(n.send("gimmietheDATA"))