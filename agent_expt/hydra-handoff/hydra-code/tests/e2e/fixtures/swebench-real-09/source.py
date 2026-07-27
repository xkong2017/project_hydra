def extract_type_hints(cls):
    hints = {}
    for attr in dir(cls):
        ann = cls.__annotations__.get(attr, None)
        if ann:
            hints[attr] = ann
    return hints
