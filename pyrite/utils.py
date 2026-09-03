from pyrite.primitives import Target

def find(predicate, iterable):
    for i, item in enumerate(iterable):
        if predicate(item): return item
    return None


def find_all(predicate, iterable):
    ret = []
    for i, item in enumerate(iterable):
        if predicate(item): ret.append(item)
    return ret

def detect_cycles(tasks):
    """
    Returns (has_cycle, cycle_path) using Kahn's algorithm.
    Runs in O(V + E) time, uses minimal memory.
    """
    # Build adjacency list
    graph = {task.name: [] for task in tasks}
    in_degree = {task.name: 0 for task in tasks}
    
    for task in tasks:
        for dep in task.requires + task.after:
            if isinstance(dep, Target):
                continue  # Targets are external, can't cycle
            if dep not in graph:
                raise ValueError(f"Task '{dep}' not found")
            graph[task.name].append(dep)
            in_degree[dep] = in_degree.get(dep, 0) + 1
    
    # Kahn's algorithm
    queue = [name for name, deg in in_degree.items() if deg == 0]
    sorted_tasks = []
    
    while queue:
        node = queue.pop()
        sorted_tasks.append(node)
        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    # If we couldn't sort all tasks, there's a cycle
    if len(sorted_tasks) != len(tasks):
        # Find the cycle (the nodes that still have in_degree > 0)
        cycle = [name for name, deg in in_degree.items() if deg > 0]
        return True, cycle
    
    return False, None