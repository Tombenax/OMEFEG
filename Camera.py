# -------------------------
# CAMERA
# -------------------------

class Camera:
    def __init__(self, pos, ctx, prog, text_prog, TEXTURE_INDICES, font_texture, charset:str, multiplayer:bool=False, serveraddress=None, serverport=None, window=None):
        self.position = np.array(pos, dtype='f4')
        self.prev_pos = self.position

        self.front = np.array([0, 0, -1], dtype='f4')
        self.up = np.array([0, 1, 0], dtype='f4')

        self.yaw = -90
        self.pitch = 0

        self.speed = 5
        self.sensitivity = 0.1

        self.vel_y = 0.0
        self.on_ground = False
        self.placed = False
        self.destroyed = False

        # physics
        self.gravity = 20
        self.jump_strength = 8
        self.max_fall = -30

        # player size (VERY IMPORTANT)
        self.height = 1.8
        self.eye_height = 1.6
        self.width = 0.3

        self.enabled = True

        self.first_mouse = True
        self.last_x = WIDTH / 2
        self.last_y = HEIGHT / 2

        self.multiplayer = multiplayer

        self.chat = InstancedText(ctx, text_prog, font_texture, charset)

        self.is_in_water = False

        if self.multiplayer:
            with open("data.txt", "r") as f:
                content = f.readlines()
                username = content[0].strip()
                password = content[1].strip()
            self.playername = username
            self.uuid = get_username_and_uuid(username, password)
            if self.uuid == "invalid credentials":
                notification("It seems like your credentials are invalid, please restart the game and re-write them.")
                with open("data.txt", "w") as f:
                    f.write("")
                glfw.set_window_should_close(window, True)
            elif self.uuid == "account disabled":
                notification("It seems like your account is disabled, if you want to play online re-enable it at https://tombenax.pythonanywhere.com/account/login")
                glfw.set_window_should_close(window, True)
            self.network = Network({"x":float(self.position[0]), "y":float(self.position[1]), "z":float(self.position[2]), "name":self.playername, "uuid":str(self.uuid)}, serveraddress, serverport)
            print("Initialized network with id of:", self.network.id)
            vertices, indices = load_obj_for_moderngl("assets/models/player.obj")
            self.players = InstancedModel(ctx,prog,vertices,indices,TEXTURE_INDICES)
            self.already_seen_placed = []
            self.already_seen_destroyed = []

    def get_world(self):
        if self.multiplayer:
            bytes_lenght = int(self.network.client.recv(2048).decode())

            _data_ = self.network.send("PLEASE,IWANTTHEWORLDPOSITIONS", recive_size=bytes_lenght)

            models = json.loads(_data_)

            bytes_lenght = int(self.network.client.recv(2048).decode())

            _data_ = self.network.send("PLEASE,IWANTTHEWORLDTEXTURES", recive_size=bytes_lenght)
            
            layers = json.loads(_data_)

            bytes_lenght = int(self.network.client.recv(2048).decode())

            _data_ = self.network.send("PLEASE,IWANTTHEWORLDATTRIBUTES", recive_size=bytes_lenght)
            
            proprieties = json.loads(_data_)

            for idx, propriety in enumerate(proprieties):
                new_dict = {}
                for i in [0, 1]:
                    new_dict[i] = INTERACT_FUNCTION_CONVERSION[propriety[i]]
                proprieties[idx] = new_dict

            return models, layers, proprieties

    # -------------------------
    # VIEW
    # -------------------------
    def get_view(self):
        eye_pos = self.position + np.array([0, self.eye_height, 0], dtype='f4')
        return Matrix44.look_at(eye_pos, eye_pos + self.front, self.up)
    # -------------------------
    # MOUSE
    # -------------------------
    def process_mouse(self, xpos, ypos):
        if not self.enabled:
            return

        if self.first_mouse:
            self.last_x = xpos
            self.last_y = ypos
            self.first_mouse = False

        xoffset = (xpos - self.last_x) * self.sensitivity
        yoffset = (self.last_y - ypos) * self.sensitivity

        self.last_x = xpos
        self.last_y = ypos

        self.yaw += xoffset
        self.pitch += yoffset
        self.pitch = max(-89, min(89, self.pitch))

        front = np.array([
            math.cos(math.radians(self.yaw)) * math.cos(math.radians(self.pitch)),
            math.sin(math.radians(self.pitch)),
            math.sin(math.radians(self.yaw)) * math.cos(math.radians(self.pitch))
        ], dtype='f4')

        self.front = front / np.linalg.norm(front)
              
    # -------------------------
    # KEYBOARD INPUT
    # -------------------------
    def process_keyboard(self, window, delta, occupied):
        if not self.enabled:
            return

        move = np.zeros(3, dtype='f4')

        right = np.cross(self.front, self.up)
        right /= np.linalg.norm(right)

        # WASD (no Y movement)
        if glfw.get_key(window, glfw.KEY_W) == glfw.PRESS:
            move += self.front
        if glfw.get_key(window, glfw.KEY_S) == glfw.PRESS:
            move -= self.front
        if glfw.get_key(window, glfw.KEY_A) == glfw.PRESS:
            move -= right
        if glfw.get_key(window, glfw.KEY_D) == glfw.PRESS:
            move += right

        move[1] = 0

        if np.linalg.norm(move) > 0:
            move = move / np.linalg.norm(move)

        speed = 10 if glfw.get_key(window, glfw.KEY_LEFT_CONTROL) == glfw.PRESS else 5
        move *= speed * delta

        # 🔥 MOVE X AND Z SEPARATELY
        self.move_axis(move[0], 0, occupied)
        self.move_axis(0, move[2], occupied)

        # 🔥 JUMP
        if (self.on_ground or self.is_in_water) and glfw.get_key(window, glfw.KEY_SPACE) == glfw.PRESS:
            self.vel_y = self.jump_strength
            self.on_ground = False

    # -------------------------
    # PHYSICS UPDATE
    # -------------------------
    def update(self, window, delta, occupied, hit, normal, block, selected_block, blocks, block_index, message_to_send:str, in_block:Block):
        if not self.multiplayer:
            if not self.enabled:
                return
        
        temp_pos = self.position.copy()
        temp_pos[1] = 0
        temp_prev_pos = self.prev_pos.copy()
        temp_prev_pos[1] = 0

        if not (temp_pos == temp_prev_pos).all():
            playsound("assets/sounds/grass.mp3")
            self.prev_pos = self.position


        blocks_broken_positions = []
        blocks_placed_positions = []

        if in_block is not None:
            if in_block.block == "water_1":
                self.gravity = 8
                self.max_fall = -2
                self.is_in_water = True
                self.jump_strength = 2
            else:
                self.gravity = 20
                self.max_fall = -30
                self.is_in_water = False
                self.jump_strength = 8
        else:
            self.gravity = 20
            self.max_fall = -30
            self.is_in_water = False
            self.jump_strength = 8
        # -------------------------
        # 🧱 BLOCK INTERACTION (RESTORED)
        # -------------------------
        if block_index is not None:
            # PLACE
            if not self.placed:
                if glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_RIGHT) == glfw.PRESS:
                    if hit and normal is not None:
                        blocks[block_index].proprieties[0](
                            block, normal, occupied, hit, blocks, selected_block, self.position
                        )
                        self.placed = True
                        blocks_placed_positions.append([(int(hit[0]), int(hit[1]), int(hit[2])), selected_block, '{0:destroy, 1:place}'])
            else:
                if glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_RIGHT) != glfw.PRESS:
                    self.placed = False

            # DESTROY
            if not self.destroyed:
                if glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_LEFT) == glfw.PRESS:
                    if hit:
                        blocks[block_index].proprieties[1](
                            block, normal, occupied, hit, blocks, selected_block, self.position
                        )
                        self.destroyed = True
                        blocks_broken_positions.append([(int(hit[0]), int(hit[1]), int(hit[2])), selected_block, '{0:destroy, 1:place}'])
            else:
                if glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_LEFT) != glfw.PRESS:
                    self.destroyed = False
            
        if glfw.get_key(window, glfw.KEY_R) == glfw.PRESS:
            self.position = np.array((0, 1, 0), dtype='f4')

        if self.multiplayer:

            recived = self.network.send("gimmietheDATA")
            if recived == "too bad idiot, your banned!!!":
                notification("I'm sorry, it seems like you have been banned, ask the server managers for the appeal")
                return "ban"
            
            alldata = json.loads(recived)
            
            packet = {
                    "network id": self.network.id,
                    "position": [float(self.position[0]), float(self.position[1]), float(self.position[2])],
                    "orientation": [float(self.yaw), float(self.pitch)],
                    "username": self.playername,
                    "blocks broken at": blocks_broken_positions,
                    "blocks placed at": blocks_placed_positions,
                    "chat message": message_to_send
                      }

            response = self.network.send(json.dumps(packet))
            if response != "recived":
                print("the server has something")

            playersdata = alldata[0]
            chat_data = alldata[1]
            blockdata_placed = alldata[2]
            blockdata_destroyed = alldata[3]


            for blo in blockdata_placed:
                if blo in self.already_seen_placed: continue
                if not tuple(blo[0]) in occupied:
                    blocks.append(Block(blo[1], blo[0], blo[1], {0:destroy, 1:place}, block))
                    occupied.add(tuple(blo[0]))

                self.already_seen_placed.append(blo)
                if len(self.already_seen_placed) > 20:
                    self.already_seen_placed.pop(0)

            for blo in blockdata_destroyed:
                if blo in self.already_seen_destroyed: continue
                if tuple(blo[0]) in occupied:
                    removal_index = block.remove_instance(tuple(blo[0]))
                    occupied.discard(tuple(blo[0]))
                    blocks.pop(removal_index)

                self.already_seen_destroyed.append(blo)
                if len(self.already_seen_destroyed) > 20:
                    self.already_seen_destroyed.pop(0)

                    
            
            self.players.models = np.zeros((0,4,4), dtype='f4')

            for playerdata in playersdata:
                self.players.add_instances(positions=[[playerdata[0], playerdata[1], playerdata[2]]], texture_names=["player"], rotations=[[math.radians(playerdata[4]), math.radians(playerdata[3]-90), 0]]) #+ALWAYS USE Z+ = FORWARD IN MODELS

            chat_owners = tuple(reversed(chat_data[0]))
            chat_messages = tuple(reversed(chat_data[1]))

            for idx in range(len(chat_owners)):
                if len(self.chat.strings) > idx:
                    self.chat.update_string(new_text=f"|{chat_owners[idx]}|:{chat_messages[idx]}", string_id=idx, pos=(-0.9, -0.9+idx/10))
                else:
                    self.chat.add_string(text=f"|{chat_owners[idx]}|:{chat_messages[idx]}", string_id=idx, pos=(-0.9, -0.9+idx/10))     


        # -------------------------
        # 🌍 PHYSICS (NEW SYSTEM)
        # -------------------------
        self.vel_y -= self.gravity * delta
        if self.vel_y < self.max_fall:
            self.vel_y = self.max_fall

        dy = self.vel_y * delta
        self.move_vertical(dy, occupied)

    # -------------------------
    # COLLISION HELPERS
    # -------------------------
    def is_blocked(self, x, y, z, occupied):
        return (int(x), int(y), int(z)) in occupied
    
    def collides(self, pos, occupied):
        px, py, pz = pos

        # player bounds
        min_x = px - self.width
        max_x = px + self.width
        min_y = py
        max_y = py + self.height
        min_z = pz - self.width
        max_z = pz + self.width

        # For blocks centered at (x, y, z), their min/max in world coords are (x-0.5, x+0.5)
        # So we adjust only x and z, not y
        x_start = int(np.floor(min_x + 0.5))
        x_end   = int(np.floor(max_x + 0.5))
        y_start = int(np.floor(min_y+0.5))
        y_end   = int(np.floor(max_y+0.5))
        z_start = int(np.floor(min_z + 0.5))
        z_end   = int(np.floor(max_z + 0.5))

        for x in range(x_start, x_end + 1):
            for y in range(y_start, y_end + 1):
                for z in range(z_start, z_end + 1):
                    if (x, y, z) in occupied:
                        return True

        return False

    # -------------------------
    # AXIS MOVEMENT (X/Z)
    # -------------------------
    def move_axis(self, dx, dz, occupied):
        new_pos = self.position + np.array([dx, 0, dz], dtype='f4')

        if not self.collides(new_pos, occupied):
            self.position = new_pos

    # -------------------------
    # VERTICAL MOVEMENT
    # -------------------------
    def move_vertical(self, dy, occupied):
        new_pos = self.position + np.array([0, dy, 0], dtype='f4')

        if dy < 0:  # falling
            if self.collides(new_pos, occupied):
                self.vel_y = 0
                self.on_ground = True
                return
        else:  # jumping
            if self.collides(new_pos, occupied):
                self.vel_y = 0
                return

        self.position = new_pos
        self.on_ground = False

    # -------------------------
    def enable(self, window):
        glfw.set_input_mode(window,glfw.CURSOR,glfw.CURSOR_DISABLED)
        self.enabled = True

    def disable(self, window):
        glfw.set_input_mode(window,glfw.CURSOR,glfw.CURSOR_NORMAL)
        self.enabled = False