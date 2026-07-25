# N17: String Escape Bug

**Bug**: HTML escaping only handles `<` and `>` but misses `&`, `"`, and `'`.

**Fix**: Escape all five HTML special characters.
