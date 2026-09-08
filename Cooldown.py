import time

class Cooldown:
    def __init__(self, time):
        self.time = time
        self.activable = True


    @property
    def is_active(self):
        if self.activable:
            self.activable = False
            self.last_activation = time.time()

            return True
        
        elif time.time() - self.last_activation >= self.time:
            self.activable = True

        return False