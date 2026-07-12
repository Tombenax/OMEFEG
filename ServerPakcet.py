import json

class PacketError(Exception):
    def __init__(self, message:str):
        self.message = message
        super().__init__(self.message)

class ServerPakcet:
    def __init__(self, default_keys:list[str], default_values:list[str]) -> None:
        """
        Creates a server packet to send, use ServerPakcet() to get the packet content's.
        Use update_packet to change a packet's key to a value.
        Use restore_defaults to restore the default packet.
        Use send to get the packet contents as json and restore the packet do the default state.
        Use packet_from_json to build a packet from json, current packet will get overridden with the output. **ONLY THE CURRENT_PACKET IS GETTING OVERRIDDEN, DEFAuLT_PACKET REMAINS THE SAME**.
        **json is used as the python package 'json'**
        """
        self.default_packet:dict[str, str] = dict(zip(default_keys, default_values))
        self.current_packet  = self.default_packet
    
    def __call__(self) -> dict[str, str]:
        return self.current_packet
    
    def update_packet(self, key:str, value:str) -> None:
        self.current_packet[key] = value
    
    def restore_defaults(self) -> None:
        self.current_packet = self.default_packet
    
    def send(self) -> str:
        temp_packet = self.current_packet
        self.restore_defaults()
        return json.dumps(temp_packet)

    def packet_from_json(self, jsoned_packet:str) -> None:
        self.current_packet:dict[str, str] = json.loads(jsoned_packet)
        if type(self.current_packet) != dict[str, str]:
            self.current_packet = self.default_packet
            raise PacketError("Incoming pakcte is not convertible into a dictionary, please assure that the packet is convertible to a dictionary")
