functions_cache = {}

import ast
import inspect
import textwrap
import threading

# Chunk generation now runs on worker threads; the remaining @cache users
# (generate_tree, square_range, ...) share this dict, so guard it.
_CACHE_LOCK = threading.Lock()


def classify_returns(func):
    try:
        source = textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError):
        # Android ships compiled .pyc without .py source (p4a also bakes
        # the host compile path into code objects), so inspect can't
        # fetch source on-device. Fall back to caching enabled: caching
        # a None return is harmless, crashing the whole app is not.
        return "return_value"
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return "return_value"

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

            key = (func, str(args), str(kwargs))

            with _CACHE_LOCK:
                if key in functions_cache:
                    return functions_cache[key]



            result = func(*args, **kwargs)

            with _CACHE_LOCK:
                functions_cache[key] = result

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