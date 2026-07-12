import pyautogui as py
import keyboard

selected_key = ""

while True:
    try:
        if keyboard.is_pressed("w"):
            selected_key = "w"
            print("selected key is w")
            break
    except:
        pass

while True:
    py.press(selected_key)
    try:
        if keyboard.is_pressed(":"):
            print("stopping")
            break
    except:
        pass