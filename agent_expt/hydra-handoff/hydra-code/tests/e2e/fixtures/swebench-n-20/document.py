import copy


class Document:
    def __init__(self, data):
        self.data = data

    def clone(self):
        return Document(dict(self.data))

    def set_metadata(self, key, value):
        self.data["metadata"] = self.data.get("metadata", {})
        self.data["metadata"][key] = value

    def get_metadata(self, key):
        meta = self.data.get("metadata", {})
        return meta.get(key)


def merge_documents(doc1, doc2):
    merged = {}
    for k, v in doc1.data.items():
        merged[k] = v
    for k, v in doc2.data.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return Document(merged)
