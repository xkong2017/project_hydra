def deep_merge(base, overlay):
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def merge_configs(defaults, user_config):
    return deep_merge(defaults, user_config)


def merge_schemas(schema_a, schema_b):
    return deep_merge(schema_a, schema_b)
