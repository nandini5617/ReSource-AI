"""ReSource AI agent with automatic multi-provider fallback."""
from __future__ import annotations

from dataclasses import dataclass, field

import database
import tools
from ai_router import AIRouterError, run_agent
from config import get_settings, is_mock_mode, redact
from memory import SessionMemory


SYSTEM_PROMPT = """You are ReSource AI, an agent that gives unused, surplus and discarded resources a second life (SecondLife) and makes smart waste decisions (WasteWise).

You are an agent, not a chatbot: use your tools instead of guessing.
Typical workflow for a new resource:
analyze_resource -> save_resource -> find_matches (by resource_id) -> get_reuse_ideas -> estimate_impact, then answer.

Skip tools that are not needed (e.g. only call list_records when asked about records).
Only call create_exchange_request when the user asks to proceed with an exchange.

Rules:
- Follow the waste hierarchy: reuse > repair > recycle > dispose. Explain WHY you chose the action.
- Only recommend organisations returned by find_matches; never invent organisations, contacts or numbers. Mention they are sample directory entries to be confirmed.
- Impact numbers must be described as ESTIMATES based on generic factors, not verified measurements.
- If the user gives no location, a default of Delhi is used: say so.
- If a tool returns an error, fix the arguments and retry once, or explain the problem.
- For possibly hazardous items (paint, chemicals, batteries, medical waste), advise authorised disposal channels.
- Use earlier information from this conversation when the user refers to it.

Exchange safety (very important):
- You can create a PENDING exchange request and cancel one. You can NOT approve, reject or complete an exchange.
- Approval (the organisation accepted) and completion (the physical hand-over happened) are confirmed by the USER with buttons in the Exchanges tab of the app.
- If the user tells you an organisation accepted or the items were handed over, do not try to change the status yourself. Tell them to confirm it in the Exchanges tab.
- Never state that an exchange is approved or completed unless a tool result or list_records output shows that status.
- Environmental impact is recorded only after the user confirms completion.

Final answer format (short, practical):
1) What it is and the decision (with reasoning)
2) Top matches with scores and reasons
3) Reuse ideas
4) Estimated impact
5) Suggested next step.
"""

# run_agent() returns these as normal text when it gives up; treat them as errors
# so they are not stored in session memory as if they were real answers.
_FAILURE_PREFIXES = (
    "I reached the step limit",
    "The AI provider returned an empty response",
)


@dataclass
class AgentResult:
    answer: str
    trace: list[dict] = field(default_factory=list)
    mock: bool = False
    error: bool = False
    provider: str | None = None


class ResourceAgent:
    def __init__(self, memory: SessionMemory | None = None):
        self.memory = memory or SessionMemory()
        database.init_db()

    # ------------------------------------------------------------ public API

    def run(self, user_message: str) -> AgentResult:
        user_message = (user_message or "").strip()

        if not user_message:
            return AgentResult(
                "Please tell me about a resource or ask a question.",
                error=True,
            )

        try:
            if is_mock_mode():
                result = self._mock_run(user_message)
            else:
                result = self._live_run(user_message)

        except AIRouterError as exc:
            result = AgentResult(
                f"AI backend error: {redact(str(exc))}",
                error=True,
            )

        except Exception as exc:  # noqa: BLE001 - the UI must never crash
            result = AgentResult(
                f"Unexpected agent error: {redact(str(exc))}",
                error=True,
            )

        if not result.error:
            self.memory.add_turn(user_message, result.answer)

        return result

    def reset(self) -> None:
        self.memory.clear()

    # ------------------------------------------------------------- live mode

    def _live_run(self, user_message: str) -> AgentResult:
        settings = get_settings()

        system = SYSTEM_PROMPT + self.memory.context_summary()

        answer, trace, provider = run_agent(
            history=self.memory.turns,
            user_message=user_message,
            system=system,
            tool_declarations=tools.TOOL_DECLARATIONS,
            dispatch=lambda name, args: tools.dispatch(
                name, args, self.memory
            ),
            max_steps=settings.max_agent_steps,
            max_tool_calls=settings.max_tool_calls,
        )

        failed = answer.startswith(_FAILURE_PREFIXES)

        return AgentResult(
            answer=answer,
            trace=trace,
            mock=False,
            error=failed,
            provider=provider,
        )

    # ------------------------------------------------------------- mock mode

    def _mock_run(self, user_message: str) -> AgentResult:
        """Offline demonstration using fixed Python tool operations."""
        trace: list[dict] = []

        def call(name: str, args: dict) -> dict:
            result = tools.dispatch(name, args, self.memory)

            trace.append({
                "tool": name,
                "args": args,
                "result": result,
            })

            return result

        # 1. Analyse the resource.
        analysis_result = call(
            "analyze_resource",
            {"description": user_message},
        )

        if "error" in analysis_result:
            return AgentResult(
                analysis_result["error"],
                trace,
                mock=True,
                error=True,
            )

        # 2. Save the resource.
        saved = call(
            "save_resource",
            {
                key: analysis_result[key]
                for key in (
                    "name",
                    "category",
                    "condition",
                    "quantity",
                    "unit",
                    "location",
                    "disposition",
                    "material",
                )
            },
        )

        if "error" in saved:
            return AgentResult(
                saved["error"],
                trace,
                mock=True,
                error=True,
            )

        resource_id = saved.get("resource_id")

        # 3. Find matching organisations.
        matches = call(
            "find_matches",
            {"resource_id": resource_id},
        )

        # 4. Generate reuse ideas.
        ideas = call(
            "get_reuse_ideas",
            {
                "name": analysis_result["name"],
                "category": analysis_result["category"],
                "material": analysis_result["material"],
                "condition": analysis_result["condition"],
            },
        )

        # 5. Estimate environmental impact.
        impact_result = call(
            "estimate_impact",
            {
                "category": analysis_result["category"],
                "quantity": analysis_result["quantity"],
                "unit": analysis_result["unit"],
                "action": analysis_result["disposition"],
            },
        )

        lines = [
            "[Offline demo mode - no cloud AI provider was called]",
            "",
            (
                f"1) Identification: {analysis_result['name']} -> "
                f"{analysis_result['category']}, condition "
                f"'{analysis_result['condition']}', "
                f"{analysis_result['quantity']:g} "
                f"{analysis_result['unit']}, "
                f"location {analysis_result['location']}."
            ),
            (
                f"   Decision: {analysis_result['disposition'].upper()}. "
                f"{analysis_result['reasoning']}"
            ),
            "",
            "2) Top matches (sample directory, confirm availability):",
        ]

        for match in matches.get("matches", [])[:3]:
            lines.append(
                f"   - {match['name']} (id {match['org_id']}, "
                f"score {match['score']}/100): "
                f"{match['reasons'][-1]}"
            )

        if not matches.get("matches"):
            lines.append(
                "   - No organisation in the directory accepts this item."
            )

        lines.extend(["", "3) Reuse ideas:"])

        for idea in ideas.get("ideas", [])[:3]:
            lines.append(
                f"   - {idea['idea']} ({idea['effort']} effort)"
            )

        lines.extend([
            "",
            f"4) Estimated impact ({impact_result['label']}):",
            (
                f"   ~{impact_result['kg_diverted']} kg diverted, "
                f"~{impact_result['co2e_avoided_kg']} kg CO2e avoided."
            ),
            "",
            (
                f"5) Next step: ask me to create an exchange request "
                f"for resource id {resource_id}. Approval and completion "
                f"are confirmed by you in the Exchanges tab."
            ),
        ])

        return AgentResult(
            answer="\n".join(lines),
            trace=trace,
            mock=True,
            error=False,
        )