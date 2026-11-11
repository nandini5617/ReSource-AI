
"""Provider-independent session memory."""
from __future__ import annotations

import database


class SessionMemory:
    def __init__(self, max_turns: int = 8):
        self.max_turns = max_turns
        self.turns: list[tuple[str, str]] = []
        self.resource_ids: list[int] = []

    def add_turn(self, user_text: str, assistant_text: str) -> None:
        self.turns.append((user_text, assistant_text))
        self.turns = self.turns[-self.max_turns:]

    def note_resource(self, resource_id: int) -> None:
        if resource_id not in self.resource_ids:
            self.resource_ids.append(resource_id)

    def contents(self) -> list:
        """Return provider-independent conversation history."""
        return [
            {"role": role, "content": text}
            for user_text, assistant_text in self.turns
            for role, text in (
                ("user", user_text),
                ("assistant", assistant_text),
            )
        ]

    def context_summary(self) -> str:
        lines = []

        for rid in self.resource_ids[-10:]:
            resource = database.get_resource(rid)

            if resource:
                lines.append(
                    f"- id {resource['id']}: {resource['name']} "
                    f"({resource['category']}, {resource['condition']}, "
                    f"{resource['quantity']:g} {resource['unit']}, "
                    f"status: {resource['status']})"
                )

        if not lines:
            return ""

        return (
            "\n\nResources already recorded in this session:\n"
            + "\n".join(lines)
        )

    def clear(self) -> None:
        self.turns = []
        self.resource_ids = []
