import sdl2
import sdl2.ext

sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER)


class ControllerHandler:
    DEADZONE = 6000

    BUTTON_NAMES = {
        sdl2.SDL_CONTROLLER_BUTTON_A: "A",
        sdl2.SDL_CONTROLLER_BUTTON_B: "B",
        sdl2.SDL_CONTROLLER_BUTTON_X: "X",
        sdl2.SDL_CONTROLLER_BUTTON_Y: "Y",

        sdl2.SDL_CONTROLLER_BUTTON_BACK: "BACK",
        sdl2.SDL_CONTROLLER_BUTTON_GUIDE: "GUIDE",
        sdl2.SDL_CONTROLLER_BUTTON_START: "START",

        sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK: "L3",
        sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK: "R3",

        sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: "L1",
        sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: "R1",

        sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP: "DU",
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN: "DD",
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT: "DL",
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT: "DR",
    }

    def __init__(self, controller_index=0):
        self.controller = None

        if sdl2.SDL_IsGameController(controller_index):
            self.controller = sdl2.SDL_GameControllerOpen(controller_index)

        self.event = sdl2.SDL_Event()

        # Inputs detected this update
        self.held = set()

        # Inputs that should only trigger once until released
        self.one_shot = {
            "DU",
            "DD",
            "DL",
            "DR",
        }

        # One-shot inputs currently being held down
        self._one_shot_down = set()

    def update(self):
        if not self.controller:
            return set()

        while sdl2.SDL_PollEvent(self.event):

            if self.event.type == sdl2.SDL_QUIT:
                self.disconnect()
                return set()

            elif self.event.type == sdl2.SDL_CONTROLLERDEVICEREMOVED:
                self.disconnect()
                return set()

        self.held.clear()
        current = set()

        # Buttons
        for button, name in self.BUTTON_NAMES.items():
            if sdl2.SDL_GameControllerGetButton(
                self.controller,
                button
            ):
                current.add(name)
                self._add_input(name)

        # Triggers
        l2 = sdl2.SDL_GameControllerGetAxis(
            self.controller,
            sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT
        )

        r2 = sdl2.SDL_GameControllerGetAxis(
            self.controller,
            sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT
        )

        if l2 > self.DEADZONE:
            current.add("L2")
            self._add_input("L2")

        if r2 > self.DEADZONE:
            current.add("R2")
            self._add_input("R2")

        # Left stick
        self._handle_stick(
            sdl2.SDL_CONTROLLER_AXIS_LEFTX,
            "LX",
            current
        )

        self._handle_stick(
            sdl2.SDL_CONTROLLER_AXIS_LEFTY,
            "LY",
            current
        )

        # Right stick
        self._handle_stick(
            sdl2.SDL_CONTROLLER_AXIS_RIGHTX,
            "RX",
            current
        )

        self._handle_stick(
            sdl2.SDL_CONTROLLER_AXIS_RIGHTY,
            "RY",
            current
        )

        # Remove released one-shot buttons
        self._one_shot_down.intersection_update(current)

        return self.held

    def _add_input(self, name):
        if name in self.one_shot:

            if name in self._one_shot_down:
                return

            self._one_shot_down.add(name)

        self.held.add(name)

    def _handle_stick(self, axis, name, current):
        value = sdl2.SDL_GameControllerGetAxis(
            self.controller,
            axis
        )

        if value > self.DEADZONE:
            current.add(name)
            self._add_input(name)

        elif value < -self.DEADZONE:
            direction = "-" + name
            current.add(direction)
            self._add_input(direction)

    def disconnect(self):
        if self.controller:
            sdl2.SDL_GameControllerClose(self.controller)
            self.controller = None