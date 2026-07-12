from proprieties_functions import functionslist

INTERACT_FUNCTION_CONVERSION = {}
#str->func
for idx in range(len(functionslist)):
    INTERACT_FUNCTION_CONVERSION[functionslist[idx][0]] = functionslist[idx][1]

REVERSE_INTERACT_FUNCTION_CONVERSION = {}

for key, value in INTERACT_FUNCTION_CONVERSION.items():
    REVERSE_INTERACT_FUNCTION_CONVERSION[value] = key