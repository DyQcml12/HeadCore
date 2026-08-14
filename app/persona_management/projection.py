from __future__ import annotations

from app.persona_management.contracts import PersonaBinding, PersonaRuntimeProjection, PersonaVersion
from app.persona_management.validation import SYSTEM_REQUIRED_GATES


def build_runtime_projection(
    version: PersonaVersion,
    binding: PersonaBinding | None = None,
) -> PersonaRuntimeProjection:
    if binding is not None and binding.version_id != version.version_id:
        raise ValueError("binding_version_mismatch")
    surface = binding.surface if binding else ()
    return PersonaRuntimeProjection(
        profile_id=version.profile_id,
        version=version.version,
        version_id=version.version_id,
        default_style=version.definition.default_style,
        core_lines=version.definition.core_lines,
        effective_gates=version.definition.enabled_gates | SYSTEM_REQUIRED_GATES,
        surface=surface,
    )


def render_runtime_projection(projection: PersonaRuntimeProjection) -> str:
    lines = [
        f"已发布人格版本：{projection.version_id}。以下内容由人格管理系统审核发布。",
        f"已发布表达风格：{projection.default_style.strip()[:1000]}",
    ]
    lines.extend(
        f"已发布人格约束：{line.strip()[:500]}"
        for line in projection.core_lines[:100]
        if line.strip()
    )
    return "\n".join(lines)
