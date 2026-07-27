def check_similar(lines, min_lines):
    similar = []
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            if lines[i] == lines[j]:
                similar.append((i, j))
    return similar
