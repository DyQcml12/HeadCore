from __future__ import annotations

from app.persona_management.contracts import (
    BindingContext,
    BindingScope,
    PersonaBinding,
)


_SCOPE_PRIORITY = {
    BindingScope.GLOBAL: 0,
    BindingScope.PLATFORM: 1,
    BindingScope.RELATIONSHIP: 2,
    BindingScope.PROFILE: 3,
    BindingScope.CONVERSATION: 4,
}


def resolve_binding(
    bindings: tuple[PersonaBinding, ...],
    context: BindingContext,
) -> PersonaBinding | None:
    keys = {
        BindingScope.GLOBAL: "*",
        BindingScope.PLATFORM: context.platform,
        BindingScope.RELATIONSHIP: context.relationship,
        BindingScope.PROFILE: context.profile_id,
        BindingScope.CONVERSATION: context.conversation_id,
    }
    matches = [
        binding
        for binding in bindings
        if binding.active and keys[binding.scope] and binding.scope_key == keys[binding.scope]
    ]
    if not matches:
        return None
    return max(matches, key=lambda binding: (_SCOPE_PRIORITY[binding.scope], binding.binding_id))

