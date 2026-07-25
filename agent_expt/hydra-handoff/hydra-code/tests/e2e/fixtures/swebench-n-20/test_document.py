from document import Document, merge_documents


def test_clone_preserves_values():
    doc = Document({"title": "Hello", "version": 1})
    cloned = doc.clone()
    assert cloned.data["title"] == "Hello"


def test_clone_isolation():
    doc = Document({"items": [1, 2, 3], "meta": {"views": 10}})
    cloned = doc.clone()
    cloned.data["meta"]["views"] = 99
    assert doc.data["meta"]["views"] == 10,         f"Expected original views=10, got {doc.data['meta']['views']}"


def test_clone_list_isolation():
    doc = Document({"items": [1, 2, 3]})
    cloned = doc.clone()
    cloned.data["items"].append(4)
    assert len(doc.data["items"]) == 3,         f"Original list should have 3 items, has {len(doc.data['items'])}"


def test_set_metadata():
    doc = Document({})
    doc.set_metadata("author", "Alice")
    assert doc.get_metadata("author") == "Alice"


def test_merge_documents():
    doc1 = Document({"config": {"theme": "dark"}})
    doc2 = Document({"config": {"font": "large"}})
    merged = merge_documents(doc1, doc2)
    assert merged.data["config"]["theme"] == "dark"
    assert merged.data["config"]["font"] == "large"
