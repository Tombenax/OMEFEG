import glfw

class Key:
    def __init__(self, window, key, mouse:bool=False, toggle:bool=False):
        self.window = window
        self.key = key
        self.pressed = False
        self.mouse = mouse
        self.toggle = toggle
        if toggle:
            self.toggle_buffer = False
            self.idk = Key(window, key, mouse, False)
    
    @property
    def is_pressed(self):
        if not self.toggle:
            if not self.mouse:
                if not self.pressed:
                    if glfw.get_key(self.window, self.key) == glfw.PRESS:
                        self.pressed = True
                        return True
                else:
                    if glfw.get_key(self.window, self.key) == glfw.RELEASE:
                        self.pressed = False
            else:
                if not self.pressed:
                    if glfw.get_mouse_button(self.window, self.key) == glfw.PRESS:
                        self.pressed = True
                        return True
                else:
                    if glfw.get_mouse_button(self.window, self.key) == glfw.RELEASE:
                        self.pressed = False
        else:
            if self.idk.is_pressed:
                if self.toggle_buffer:
                    self.toggle_buffer = False
                else:
                    self.toggle_buffer = True
                    
            return self.toggle_buffer

        
        return False