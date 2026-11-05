from Vec3 import Vec3

from World import World

#Player states

STANDING = 0
WALKING = 1
RUNNING = 2
FLYING = 3
FALLING = 4

class Player:
    def __init__(self, render):
        self.camera = render.CAMERA
        self.state = STANDING
        self.pos = self.camera.position

    def update(self, world:World):
        self.camera.update(world.get_important_collisions(self.pos), world)

        self.pos = self.camera.position

        if world.get_block_at(self.pos - Vec3(0, 1, 0)) is None:
            self.state = FALLING

        elif self.camera.sprint:
            self.state = RUNNING

        elif self.camera.fly:
            self.state = FLYING

        else:
            self.state = STANDING

    def set_pos(self, pos: Vec3):
        self.camera.position = pos.copy()
        self.pos = self.camera.position