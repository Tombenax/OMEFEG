import tkinter as tk
import subprocess
import time
import sys
import os
from pathlib import Path

root = tk.Tk()

root.title("OMEFEG Launcher")

root.geometry("600x600")

root.resizable(False, False)

open_omefeg = False

values = {}

def open_omefeg_flag():
    global open_omefeg, values
    open_omefeg = True
    values["multiplayer_ip"] = multiplayer_ip.get()
    root.destroy()

MULTIPLAYER = False

def set_flag(flag, state, *args):
    globals()[flag] = state

    if args:
        if isinstance(args[0], tk.Button):
            args[0].config(text = args[1] if args[0].cget("text") == args[2] else args[2])

def clear_log_chache():
    for file in os.listdir("logs"):
        os.remove("logs/"+file)

launch = tk.Button(root, text="Launch OMEFEG", command=open_omefeg_flag)
launch.pack(pady=20)

select_multiplayer = tk.Button(root, text="Turn Multiplayer ON", command=lambda: set_flag("MULTIPLAYER", True, select_multiplayer, "Turn Multiplayer OFF", "Turn Multiplayer ON"))
select_multiplayer.pack(pady=20, padx=20)

multiplayer_i_txt = tk.Label(root, text="Input serer IP below")
multiplayer_i_txt.pack(pady=20, padx=20)

multiplayer_ip = tk.Entry(root)
multiplayer_ip.pack(pady=20, padx=20)

clear_log_ch = tk.Button(root, text="Clear Log Chache", command=clear_log_chache)
clear_log_ch.pack(pady=20, padx=20)

root.mainloop()

if open_omefeg:
    if Path("OMEFEG.py").exists(): command = "python OMEFEG.py"
    else: command = "OMEFEG.exe"

    if values["multiplayer_ip"].startswith("NOMOVEWINDOW"):
        print("Scret Unlocked!! Removing window moing...")
        values["multiplayer_ip"] = values["multiplayer_ip"].removeprefix("NOMOVEWINDOW")
        command += f" --not_move_window True"

    if MULTIPLAYER:
        print(f"Conncting to srever:", values["multiplayer_ip"])
        command += f" --multiplayer {values["multiplayer_ip"]}"

    print("Executing game with command:", command)

    log_time = time.time()

    with open(f"logs/log_{log_time}.txt", "w") as log:
        process = subprocess.Popen(command, shell=True, stderr=log, stdout=log)
        returncode = process.wait()

    if returncode != 0:
        print("The gam crashed with a return code of:", returncode)
        print("Logs:")
        with open(f"logs/log_{log_time}.txt", "r") as f:
            print(f.read())
        
    print(f"Logs at \"logs/log_{log_time}.txt\"")

    print("The game has stopped running, exiting...")
