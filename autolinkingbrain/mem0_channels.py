"""Mem0 channel naming helpers (no Chroma/Mem0 imports)."""


def classify_scope(user_id: str) -> str:
    if user_id == "global_skills":
        return "global"
    if user_id == "global_topology":
        return "topology"
    if user_id.startswith("project_"):
        return "project"
    return "other"
