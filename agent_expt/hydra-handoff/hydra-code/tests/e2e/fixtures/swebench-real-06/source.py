def read_source(app, filename):
    for hook in app._hooks:
        filename = hook(filename)
    with open(filename) as f:
        return f.read()
