from Render import Collectible, WIDTH, HEIGHT
from Vec3 import Vec3
from allBlocks import *
from Cooldown import Cooldown
from allBlocks import *

from utils import SoundPlayer, clip

from World import World

#Player states

STANDING = 0
WALKING = 1
RUNNING = 2
FLYING = 3
FALLING = 4

sp = SoundPlayer()

class Player:
    def __init__(self, render):

        self.render = render

        self.camera = render.CAMERA
        self.state = STANDING
        self.pos = self.camera.position

        self.inventory = {}
        self.inventory_list = []
        self.inventory_slots = 2

        self.head_slot = None
        self.chest_slot = None
        self.feet_slot = None

        self.invitems = Collectible(render)

        self.selected = 0

        self.change_selected_cooldown = Cooldown(0.2)

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

        if self.render.get_key(self.render.KEY_G) and self.change_selected_cooldown.is_active:
            if len(self.inventory_list) > 0:
                #switch chest slot and item

                self.invitems.remove_all()

                #check if an item is in chest slot
                if self.chest_slot is not None:
                    #there is an item in the chest slot

                    prev_thing = self.inventory_list[self.selected]

                    self.inventory_list[self.selected] = self.chest_slot

                    self.chest_slot = prev_thing

                    replacement = {self.inventory_list[self.selected]: self.chest_slot}

                    for k, v in list(self.inventory.items()):
                        self.inventory[replacement.get(k, k)] = self.inventory.pop(k)

                
                else:

                    self.chest_slot = self.inventory_list[self.selected]

                    self.inventory.pop(self.inventory_list[self.selected])

                    self.inventory_list.pop(self.selected)


                self.selected = clip(self.selected, len(self.inventory)-1, 0) #clip it so it doesn't go out of bounds

                self.rebuild_inv()

                if self.chest_slot == BACKPACK:
                    self.inventory_slots = 12


        if self.render.get_key(self.render.KEY_RIGHT_ARROW) and self.change_selected_cooldown.is_active:

            self.selected = min(len(self.inventory)-1, self.selected + 1)

            self.invitems.remove_all()

            self.rebuild_inv()


        if self.render.get_key(self.render.KEY_LEFT_ARROW) and self.change_selected_cooldown.is_active:

            self.selected = max(0, self.selected - 1)

            self.invitems.remove_all()

            self.rebuild_inv()

        if self.render.get_key(self.render.KEY_LEFT_SHIFT) and self.change_selected_cooldown.is_active:
            if len(self.inventory) > 0:
                self.invitems.remove_all()

                self.inventory.pop(self.inventory_list[self.selected])

                self.inventory_list.pop(self.selected)

                self.selected = clip(self.selected, len(self.inventory)-1, 0) #clip it so it doesn't go out of bounds

                self.rebuild_inv()

    def rebuild_inv(self):
        for idx, item in enumerate(self.inventory):
            self.invitems.add_collectibles([Vec3((WIDTH/2-16) + 50*idx - 50*self.selected, HEIGHT - 40.5, 0)], [item])


    def get_selcted_block(self):
        try:

            if self.inventory_list[self.selected] != "backpack":
                return self.inventory_list[self.selected]
            else:
                return None
            
        except:

            return None

    def render_2D_stuff(self):
        self.invitems.render()

    def set_pos(self, pos: Vec3):
        self.camera.position = pos.copy()
        self.pos = self.camera.position

    def add_item_in_inventory(self, item_id):

        if item_id in self.inventory:
            self.inventory[item_id] += 1

            sp.playsound("assets/sounds/pickup.wav", sound_position=(0, 0, 0))

            return True

        else:

            if len(self.inventory)+1 <= self.inventory_slots: #+1 bcause of the added item

                self.inventory[item_id] = 1

                self.inventory_list.append(item_id)

                self.invitems.add_collectibles([Vec3((WIDTH/2-16) + 50*(len(self.inventory)-1), HEIGHT - 40.5, 0)], [item_id])

                sp.playsound("assets/sounds/pickup.wav", sound_position=(0, 0, 0))

                return True

        return False