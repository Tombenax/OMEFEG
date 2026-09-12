# OMEFEG
This is my game OMEFEG (it's an achronhym, i'm not gonna reveale it)

(btw orry for my typing, but my keaboard is new and i'm getting used to it)

#

### CONTENT

- go around using WASD
- use your mouse to look around
- press 'f' an WAS or D to fly around
- space to jump
- LMB place
- RMB destroy

#

### MULTIPLAYER

As of 08/09/2026 (DD/MM/YYYY) there is no server.exe, just serer.py.

Install python from python.org (python 3.13)
Open CMD or powershell and type 'pip install socket'

then, open 'main.py' not serr.py but main.py an run it by writing in CMD or powershell 'python main.py'

Once it starts, copy the IP of your computer, open Launcher.exe an in the Entry typ the IP of your computer followed by :44699.

Click on the button tat says 'Turn Multiplayer ON' and then click on 'Launch OMEFEG'

if you did everythng wright you should connect to the server.

If you can't see any players that are connected then it's probably that the serer didn't start or that you typed something worng, so close OMEFEG an open the logs folder, open the lates log file and read the log, if there is no error then check the server terminal.

More trubleshooting coming later.

#

### MODDING
Modding is new, so it may be not fully supporte.

Then make a Mod.py file and import OMOMEFEGINTERFACER, then use the function provided by te moule.

here's a test mod that i made:
mods/TestMod/Mod.py:
import OMEFEGINTERFACER


def init(global_variables):
    OMEFEGINTERFACER.init_interfacer(global_variables)
    OMEFEGINTERFACER.move_player(0, 50, 0)
    OMEFEGINTERFACER.send_notification("TestMod", "=)=)=)=)=)=)=)=)=)=)=)=)=)=)=)=)=)=)=)=)")
    OMEFEGINTERFACER.place("oak_log", 0, 10, 0)
    OMEFEGINTERFACER.destroy(0, 0, 0)

def update():
    camera_pos = list(map(round, OMEFEGINTERFACER.get_camera().position.tolist()))
    camera_pos[1] -= 1
    OMEFEGINTERFACER.destroy(*camera_pos)

this simple mod on init sends a notification, moves the player at y 50, places an oak log and destroyes a block, in update it removes the block below the player.

as you can see moding is simple, if you want to get a game variable that is not get_camera you can use get_variable (btw if the variable does not exist the game errors)

ATTENTION:
the game uses the exec funtion to execute your mod code, bcause i didn't want to write a parser. so some mods can be malicious, only install mods by trusted sources (like me =))

#
### DEVELOPER STUFF
So, for who downloads th code and runs it (including me) here's how to run 2 versions:
- Desktop: run it on your pc by doing (in powershell) $env:OMEFEG_DESKTOP = '1' and then python OMEFEG.py

- Mobile: in powershell run $env:OMEFEG_DESKTOP = '0' and then python OMEFEG.py