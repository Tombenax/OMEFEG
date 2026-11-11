data = []

name = input("Input the .txt structur to convert (include .txt): ")

x, y, z, t = None, None, None, None

with open("worldgeneration/structures/"+name) as f:
    for line in f.readlines():
        line = line.strip()

        if not x:
            x = line

        elif not y:
            y = line

        elif not z:
            z = line

        elif not t:
            t = line

        if x and y and z and t:
            data.append([x, y, z, t])

            x, y, z, t = None, None, None, None

import json

with open("worldgeneration/structures/"+name.replace(".txt", ".json"), "w") as f:

    json.dump({"blocks":data}, f)


print("Done")