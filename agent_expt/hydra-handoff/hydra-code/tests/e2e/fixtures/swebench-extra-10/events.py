class EventStore:
    def __init__(self, max_events=100):
        self._events = []
        self._max_events = max_events

    def add(self, event):
        self._events.append(event)

    def get_recent(self, count=10):
        return self._events[-count:]

    def count(self):
        return len(self._events)

    def get_by_type(self, event_type):
        return [e for e in self._events if e.get("type") == event_type]


class EventProcessor:
    def __init__(self):
        self._processed = []

    def process(self, event):
        self._processed.append(event)
        if len(self._processed) > 100:
            self._processed.pop(0)
