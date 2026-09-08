"""Small helpers shared by database-backed access control."""


def allowed_names(global_enabled, role_allowed: str | tuple[str, ...]):
    if role_allowed == "*":
        return global_enabled
    role_set = set(role_allowed)
    if global_enabled is None:
        return sorted(role_set)
    return [name for name in global_enabled if name in role_set]
