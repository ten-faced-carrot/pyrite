

def find(predicate, iterable):
    for i, item in enumerate(iterable):
        if predicate(item): return item
    return None


def find_all(predicate, iterable):
    ret = []
    for i, item in enumerate(iterable):
        if predicate(item): ret.append(item)
    return ret

# When eventually writing predicates becomes too annoying, I'll add a .get(iterable, **attributes) function but right now I don't need it.