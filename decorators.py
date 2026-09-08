functions_cache = {}

import ast
import inspect
import textwrap


def classify_returns(func):
    source = textwrap.dedent(inspect.getsource(func))
    tree = ast.parse(source)

    returns = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Return)
    ]

    if not returns:
        return "no_return"

    for node in returns:
        if node.value is None:
            return "bare_return"

        if isinstance(node.value, ast.Constant) and node.value.value is None:
            return "return_none"

    return "return_value"

def cache(func):

    should = classify_returns(func) == "return_value"

    def inner(*args, **kwargs):

        if should:

            if a := functions_cache.get((func, str(args), str(kwargs))):
                return a



            result = func(*args, **kwargs)

            functions_cache[(func, str(args), str(kwargs))] = result

            return result

        return func(*args, **kwargs)
        

    return inner

"""
@chace
def add(x, y):
    time.sleep(5)
    return x + y

print(add(10, 5))
print(add(10, 5))
print(add(10, 5))
print(add(5, 5))
print(functions_cache)
"""