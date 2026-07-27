def strip_unused(query, used_annotations):
    result = {}
    for k, v in query.items():
        if k in used_annotations:
            result[k] = v
    return result
