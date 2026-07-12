"""
A Python tool to convert java animations (this script is based on blockbench's modded entity) and converts them into rotationanimation, positionanimation or positionrotationanimation
Takes in: java file.
Spits out: an animation file, the type is based on the contents of the java file
!!! the output path is only composed of the directories, the file is created by the program
"""

from ast import literal_eval
import os
from AnimationHandler import AnimationError


def float_range(start:float, stop:float, step:float):
    start_decimal_lenght = len(str(start))-1-str(start).find(".")
    stop_decimal_lenght = len(str(stop))-1-str(stop).find(".")
    step_decimal_lenght = len(str(step))-1-str(step).find(".")
    max_decimal_lenght = 10 ** max(start_decimal_lenght, stop_decimal_lenght, step_decimal_lenght)
    
    start *= max_decimal_lenght
    stop *= max_decimal_lenght
    step *= max_decimal_lenght

    return [j/max_decimal_lenght for j in range(int(start), int(stop), int(step))]


def range_negative(start, stop, step):
    if stop == start:
        return [start]
    if stop < start:
        return [-j for j in float_range(-start, -stop, step)]
    else:
        return list(float_range(start, stop, step))

def forced_range(start, stop, step, lenght):
    """makes a range that is less than the lenght exactly the lenght (ex. forced_range(0, 10, 1, 100) = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 9](len = 100))"""
    result = range_negative(start, stop, step)
    last_result = result[-1]
    if len(result) < lenght:
        for i in range(lenght - len(result)):
            result.append(last_result)
    
    return result



def convert_java_into_animation(java_path:str, output_path:str="assets/animations", animation_duration_seconds:float=1, wantedFPS:float=60):
    keyframes_lines:list[str] = []
    complete_lines:list[tuple[float, tuple[float, float, float]]] = []
    is_rotated = False
    is_moved = False
    file_end = ""
    types = []

    with open(java_path, "r") as java:
        for line in java.readlines():
            line = line.strip()
            if "new Keyframe" in line:
                keyframes_lines.append(line)
    
    for keyframe in keyframes_lines:
        keyframe_elements = keyframe.removeprefix("new Keyframe(").split(", ")
        keyframe_num = keyframe_elements[0]
        keyframe_instruction = keyframe_elements[1]+", "+keyframe_elements[2]+", "+keyframe_elements[3]
        keyframe_type = keyframe_elements[4]
        keyframe_instruction = keyframe_instruction.removeprefix("KeyframeAnimations.")
        keyframe_type = keyframe_type.removeprefix("AnimationChannel.Interpolations.")
        keyframe_num = float(keyframe_num.replace("F", ""))

        if "scaleVec" in keyframe_instruction:
            print(AnimationError("scale is not supported, it will be soon (maybe)! Skipping over the line."))
            continue

        if not "LINEAR" in keyframe_type:
            print(AnimationError("ONLY LINEAR type is supported!!"))

        if "degreeVec" in keyframe_instruction:
            tupled_keyframe_instruction_0 = keyframe_instruction.removeprefix("degreeVec")
            tupled_keyframe_instruction = ""
            for char in tupled_keyframe_instruction_0:
                if not char == "F":
                    tupled_keyframe_instruction += char
            
            complete_lines.append((keyframe_num, literal_eval(tupled_keyframe_instruction)))
            types.append("rotation")
            is_rotated = True

        elif "posVec" in keyframe_instruction:
            tupled_keyframe_instruction_0 = keyframe_instruction.removeprefix("posVec")
            tupled_keyframe_instruction = ""
            for char in tupled_keyframe_instruction_0:
                if not char == "F":
                    tupled_keyframe_instruction += char
            
            complete_lines.append((keyframe_num, literal_eval(tupled_keyframe_instruction)))
            types.append("position")
            is_moved = True
    
    prev_keyframe = None
    prev_keyframe_type = None
    points_x:list[list[float, float, float]] = []
    points_y:list[list[float, float, float]] = []
    points_z:list[list[float, float, float]] = []
    positions_x:list[list[float, float, float]] = []
    positions_y:list[list[float, float, float]] = []
    positions_z:list[list[float, float, float]] = []

    for keyframe, type in zip(complete_lines, types):
        if prev_keyframe == None:
            prev_keyframe = keyframe
            prev_keyframe_type = type
            continue
        
        if type != prev_keyframe_type:
            prev_keyframe_type = type
            prev_keyframe = keyframe
            continue

        for num in [0, 1, 2]:
            keyframe_numbertime = abs(abs(keyframe[1][num])-abs(prev_keyframe[1][num]))
            thing1 = ((wantedFPS-2)*(keyframe[0]-prev_keyframe[0]))
            for i in forced_range(prev_keyframe[1][num], keyframe[1][num], (keyframe_numbertime/thing1) if thing1 > 0 else float("inf"), wantedFPS-1):
                if type == "rotation":
                    if num == 0:
                        points_x.append(i)
                    elif num == 1:
                        points_y.append(i)
                    else:
                        points_z.append(i)
                elif type == "position":
                    if num == 0:
                        positions_x.append(i)
                    elif num == 1:
                        positions_y.append(i)
                    else:
                        positions_z.append(i)

        prev_keyframe = keyframe
        prev_keyframe_type = type
        
        if type == "rotation":
            points_x.append(keyframe[1][0])
            points_y.append(keyframe[1][1])
            points_z.append(keyframe[1][2])
        elif type == "position":
            positions_x.append(keyframe[1][0])
            positions_y.append(keyframe[1][1])
            positions_z.append(keyframe[1][2])
        

                


    if is_rotated and not is_moved:
        file_end = ".rotationanimation"
    elif is_moved and not is_rotated:
        file_end = ".positionanimation"
    elif is_moved and is_rotated:
        file_end = ".positionrotationanimation"

    output_file_path = output_path+"/"+os.path.splitext(os.path.basename(java_path))[0]+file_end

    with open(output_file_path, "w") as output:
        if is_rotated and not is_moved:
            for i in range(len(points_x)):
                output.write(f"{points_x[i]},{points_y[i]},{points_z[i]}\n")
        elif is_moved and not is_rotated:
            for i in range(len(positions_x)):
                output.write(f"{positions_x[i]/16},{positions_y[i]/16},{positions_z[i]/16}\n")
        elif is_moved and is_rotated:
            for i in range(len(positions_x)):
                output.write(f"{positions_x[i]/16},{positions_y[i]/16},{positions_z[i]/16},{points_x[i]},{points_y[i]},{points_z[i]}\n")
        


def merge_positionanimation_and_rotationanimation(rotationfilepath:str, positionfilepath:str, destination:str):
    with open(rotationfilepath, "r") as rot:
        rotlines = rot.readlines()
        for idx, a in enumerate(rotlines):
            rotlines[idx] = literal_eval(a.strip())

    with open(positionfilepath, "r") as pos:
        poslines = pos.readlines()
        for idx, a in enumerate(poslines):
            poslines[idx] = literal_eval(a.strip())
    

    r_len = len(rotlines)-1
    with open(destination, "w") as des:
        for idx, (rot, pos) in enumerate(zip(rotlines, poslines)):
            if not idx == r_len:
                des.write(f"{pos[0]},{pos[1]},{pos[2]},{rot[0]},{rot[1]},{rot[2]}\n")
            else:
                des.write(f"{pos[0]},{pos[1]},{pos[2]},{rot[0]},{rot[1]},{rot[2]}")








convert_java_into_animation("C:\\Users\\Tommaso\\Downloads\\model.java", animation_duration_seconds=5.75)