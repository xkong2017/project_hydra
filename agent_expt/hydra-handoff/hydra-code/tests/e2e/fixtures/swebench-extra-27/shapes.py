class Shape:
    def area(self):
        return 0

    def describe(self):
        return f"Shape at origin"


class ColoredShape(Shape):
    def __init__(self, color):
        self.color = color

    def describe(self):
        return f"Colored {self.color} Shape"


class SizedShape(Shape):
    def __init__(self, size):
        self.size = size

    def describe(self):
        return f"Sized {self.size} Shape"


class ColoredSizedShape(ColoredShape, SizedShape):
    def __init__(self, color, size):
        ColoredShape.__init__(self, color)
        SizedShape.__init__(self, size)
