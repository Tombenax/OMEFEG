from DesktopRender import InstancedModel
from math import radians
import threading
import time

class AnimationHandler:
    def __init__(self, instacnedmodel:InstancedModel, instancedmodelindex:int, animationpath:str, loop:bool=False):
        self.instacnedmodel = instacnedmodel
        self.animationpath = animationpath
        self.instacnedmodelindex = instancedmodelindex
        self.currentframe = 0
        self.loop = loop
        self.animationisrunning = False
        self.constructanimation()
    
    def constructanimation(self):
        """takes a AnimationHandler and constructs the instructions for rotating or moving an instance"""
        if self.animationpath.endswith(".rotationanimation"):
            with open(self.animationpath, "r") as animationfile:
                lines = animationfile.readlines()
                self.animationinstructions = []
                for l in lines:
                    if l == "\n": continue
                    l = l.strip().split(",")
                    self.animationinstructions.append([radians(float(l[0])), radians(float(l[1])), radians(float(l[2]))])
        elif self.animationpath.endswith(".positionanimation"):
            with open(self.animationpath, "r") as animationfile:
                lines = animationfile.readlines()
                self.animationinstructions = []
                for l in lines:
                    if l == "\n": continue
                    l = l.strip().split(",")
                    self.animationinstructions.append([float(l[0]), float(l[1]), float(l[2])])
        elif self.animationpath.endswith(".positionrotationanimation"):
            with open(self.animationpath, "r") as animationfile:
                lines = animationfile.readlines()
                self.animationinstructions = []
                for l in lines:
                    if l == "\n": continue
                    l = l.strip().split(",")
                    self.animationinstructions.append([float(l[0]), float(l[1]), float(l[2]), radians(float(l[3])), radians(float(l[4])), radians(float(l[5]))])
        else:    
            raise FileNotFoundError("The file in the path is the wrong extension, please use '.rotationanimation' or '.positionanimation' or '.positionrotationanimation'.\nFor more info visit: https://tombenax.pythonanywhere.com/animations/rotationanimation or https://tombenax.pythonanywhere.com/animations/positionanimation or https://tombenax.pythonanywhere.com/animations/positionrotationanimation")
    
    def background_loop(self):
        delay_s = 1 / self.FPS
        while self.animationisrunning:
            self.step_animation()
            time.sleep(delay_s)

    def run_animation(self, FPS:int=60):
        self.FPS = FPS
        if not self.animationisrunning:
            self.animationisrunning = True
            thread = threading.Thread(target=self.background_loop, daemon=True)
            thread.start()
    
    def stop_animation(self):
        if self.animationisrunning:
            self.animationisrunning = False

    
    def step_animation(self):
        if self.currentframe >= len(self.animationinstructions):
            self.currentframe = 0
            if not self.loop:
                self.stop_animation()
                return
        if self.animationpath.endswith(".rotationanimation"):
            self.instacnedmodel.rotate_instance(self.instacnedmodelindex, self.animationinstructions[self.currentframe])
        elif self.animationpath.endswith(".positionanimation"):
            self.instacnedmodel.move_instance(self.instacnedmodelindex, self.animationinstructions[self.currentframe])
        elif self.animationpath.endswith(".positionrotationanimation"):
            self.instacnedmodel.move_instance(self.instacnedmodelindex, self.animationinstructions[self.currentframe][:3])
            self.instacnedmodel.rotate_instance(self.instacnedmodelindex, self.animationinstructions[self.currentframe][3:])

        self.currentframe += 1


class AnimationError:
    def __init__(self, message:str):
        self.message = message
    
    def __str__(self):
        return self.message
