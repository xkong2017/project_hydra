class TreeNode:
    def __init__(self, value, children=None):
        self.value = value
        self.children = children or []

    def add_child(self, child):
        self.children.append(child)


def find_node(root, target):
    if root.value == target:
        return root
    if not root.children:
        return None
    for child in root.children:
        return find_node(child, target)
    return None


def tree_depth(root):
    if not root.children:
        return 0
    return 1 + max(tree_depth(child) for child in root.children)


def count_nodes(root):
    count = 1
    for child in root.children:
        count += count_nodes(child)
    return count
