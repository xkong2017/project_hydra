class Blueprint:
    _registered = []

    def __init__(self, name, import_name):
        self.name = name
        self.import_name = import_name

    def register(self, app):
        self._registered.append(self)
        app.register_blueprint(self)
