from tree import TreeNode, find_node


def test_find_root():
    root = TreeNode("a")
    assert find_node(root, "a") is root


def test_find_first_child():
    root = TreeNode("a")
    child = TreeNode("b")
    root.add_child(child)
    assert find_node(root, "b") is child


def test_find_second_child():
    root = TreeNode("a")
    root.add_child(TreeNode("b"))
    root.add_child(TreeNode("c"))
    result = find_node(root, "c")
    assert result is not None, "Should find second child"
    assert result.value == "c"


def test_find_nonexistent():
    root = TreeNode("a")
    assert find_node(root, "z") is None


def test_find_deep_child():
    root = TreeNode("a")
    mid = TreeNode("b")
    deep = TreeNode("c")
    root.add_child(mid)
    mid.add_child(deep)
    result = find_node(root, "c")
    assert result is not None
    assert result.value == "c"


def test_deep_tree():
    root = TreeNode("a")
    current = root
    for i in range(500):
        new = TreeNode(str(i))
        current.add_child(new)
        current = new
    result = find_node(root, "400")
    assert result is not None
    assert result.value == "400"
