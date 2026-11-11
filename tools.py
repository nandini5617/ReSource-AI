"""The agent's tools: declarations shown to the AI + the Python that runs them.

SAFETY MODEL
------------
* dispatch() is the ONLY entry point the AI can reach. Through it the AI may
  create a request and CANCEL one. It can never approve, reject or complete.
* confirm_exchange_approval / confirm_exchange_completion / reject_exchange are
  for the human-operated UI only. They are NOT in _HANDLERS and NOT in
  TOOL_DECLARATIONS, so the model cannot call them.
"""
from __future__ import annotations

import analysis
import database
import impact
import knowledge as K
import matching
from config import redact
from gemini_client import GeminiError


class ToolError(Exception):
    """A problem the model can read and correct (bad argument, missing record)."""


# -------------------------------------------------------- argument helpers
def _opt_int(v):
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        raise ToolError(f"Expected a whole number, got {v!r}.")


def _float(v, default=1.0):
    if v in (None, ""):
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ToolError(f"Expected a number, got {v!r}.")
    if f <= 0:
        raise ToolError("Quantity must be greater than zero.")
    return f


def _choice(v, allowed, field, default=None):
    if v in (None, ""):
        if default is not None:
            return default
        raise ToolError(f"'{field}' is required. Allowed: {', '.join(allowed)}.")
    s = str(v).strip().lower()
    if s not in allowed:
        raise ToolError(f"Invalid {field} '{v}'. Allowed: {', '.join(allowed)}.")
    return s


# ---------------------------------------------------------------- handlers
def _analyze(a, memory):
    return analysis.analyze_resource(str(a.get("description", "")))


def _save(a, memory):
    category = _choice(a.get("category"), K.CATEGORIES, "category")
    condition = _choice(a.get("condition"), K.CONDITIONS, "condition")
    unit = _choice(a.get("unit"), K.UNITS, "unit", default="pieces")
    disposition = _choice(a.get("disposition"), K.DISPOSITIONS, "disposition", default="reuse")
    name = str(a.get("name") or "").strip()
    if not name:
        raise ToolError("'name' is required.")
    rid = database.add_resource(
        name[:80], category, str(a.get("material") or category), condition,
        _float(a.get("quantity")), unit, str(a.get("location") or K.DEFAULT_CITY),
        disposition, str(a.get("notes") or ""),
    )
    if memory is not None:
        memory.note_resource(rid)
    return {"resource_id": rid, "status": "available", "saved": True}


def _find_matches(a, memory):
    rid = _opt_int(a.get("resource_id"))
    if rid:
        r = database.get_resource(rid)
        if not r:
            raise ToolError(f"No resource with id {rid}.")
        category, condition = r["category"], r["condition"]
        quantity, unit = r["quantity"], r["unit"]
        location, disposition = r["location"], r["disposition"]
    else:
        category = _choice(a.get("category"), K.CATEGORIES, "category")
        condition = _choice(a.get("condition"), K.CONDITIONS, "condition", default="good")
        quantity = _float(a.get("quantity"))
        unit = _choice(a.get("unit"), K.UNITS, "unit", default="pieces")
        location = str(a.get("location") or K.DEFAULT_CITY)
        disposition = a.get("disposition")
        disposition = disposition if disposition in K.DISPOSITIONS else None
    matches = matching.find_matches(category, quantity, unit, condition, location, disposition)
    note = ("Scores are computed against the SAMPLE organisation directory; "
            "availability must be confirmed with the organisation.")
    if not matches:
        note = "No organisation in the directory accepts this item/condition. Suggest generic recycling or disposal guidance."
    return {"matches": matches, "note": note}


def _ideas(a, memory):
    category = _choice(a.get("category"), K.CATEGORIES, "category")
    return analysis.generate_reuse_ideas(
        str(a.get("name") or category), category,
        str(a.get("material") or ""), str(a.get("condition") or "fair"),
    )


def _impact(a, memory):
    category = _choice(a.get("category"), K.CATEGORIES, "category")
    unit = _choice(a.get("unit"), K.UNITS, "unit", default="pieces")
    action = _choice(a.get("action"), K.DISPOSITIONS, "action")
    return impact.estimate(category, _float(a.get("quantity")), unit, action)


def _create_exchange(a, memory):
    rid, oid = _opt_int(a.get("resource_id")), _opt_int(a.get("org_id"))
    if not rid or not oid:
        raise ToolError("Both resource_id and org_id are required.")
    resource, org = database.get_resource(rid), database.get_org(oid)
    if not resource:
        raise ToolError(f"No resource with id {rid}. Save it first with save_resource.")
    if not org:
        raise ToolError(f"No organisation with id {oid}.")

    # Consistency guards: one physical item can only be in one live exchange,
    # and a transferred item cannot be offered again (prevents double-counted impact).
    if resource["status"] == "transferred":
        raise ToolError(f"Resource {rid} has already been transferred and cannot be requested again.")
    for ex in database.list_exchanges(10000):
        if ex["resource_id"] == rid and ex["status"] in ("pending", "approved"):
            raise ToolError(
                f"Resource {rid} already has an active exchange (id {ex['id']}, "
                f"status '{ex['status']}'). Cancel it first to request a different organisation."
            )

    eid = database.create_exchange(rid, oid, str(a.get("message") or ""))
    database.set_resource_status(rid, "requested")
    result = {"exchange_id": eid, "status": "pending",
              "resource": resource["name"], "organisation": org["name"]}
    if resource["category"] not in org["accepts"].split(","):
        result["warning"] = "This organisation does not normally accept this category."
    return result


# ------------------------------------------------ exchange state transitions
def _apply_transition(ex: dict, new_status: str) -> dict:
    """Shared by the AI path (cancel only) and the user-only functions.

    This is the single place where exchange status changes and impact is logged.
    """
    current = ex["status"]
    if new_status not in K.ALLOWED_TRANSITIONS.get(current, set()):
        allowed = sorted(K.ALLOWED_TRANSITIONS.get(current, set())) or ["none (final state)"]
        raise ToolError(
            f"Cannot move from '{current}' to '{new_status}'. Allowed: {', '.join(allowed)}."
        )

    resource = database.get_resource(ex["resource_id"])
    org = database.get_org(ex["org_id"])

    if new_status == "completed":
        if not resource or not org:
            raise ToolError("Cannot complete: the resource or organisation record is missing.")
        if resource["status"] == "transferred":
            raise ToolError("This resource is already marked as transferred.")

    database.set_exchange_status(ex["id"], new_status)
    result = {"exchange_id": ex["id"], "status": new_status}

    if new_status == "completed":
        est = impact.estimate(resource["category"], resource["quantity"],
                              resource["unit"], org["role"])
        database.log_impact(ex["id"], resource["id"], resource["category"], org["role"],
                            est["kg_diverted"], est["co2e_avoided_kg"])
        database.set_resource_status(resource["id"], "transferred")
        result["impact_logged"] = est
    elif new_status in ("rejected", "cancelled") and resource:
        database.set_resource_status(resource["id"], "available")

    return result


def _update_exchange(a, memory):
    """AI-facing. The AI may only CANCEL; humans approve/reject/complete via the UI."""
    eid = _opt_int(a.get("exchange_id"))
    new_status = _choice(a.get("status"), K.EXCHANGE_STATUSES, "status")

    ex = database.get_exchange(eid) if eid else None
    if not ex:
        raise ToolError(f"No exchange with id {eid}.")
    current_status = ex["status"]

    # Never allow the AI to silently approve an exchange.
    if new_status == "approved" and current_status == "pending":
        raise ToolError(
            "Approval requires explicit confirmation from the user "
            "that the organisation has accepted the exchange. "
            "Ask the user for confirmation first."
        )

    # Never allow completion without a previously approved exchange.
    if new_status == "completed" and current_status != "approved":
        raise ToolError(
            "Cannot complete this exchange. It must first be approved "
            "after confirmed acceptance from the organisation."
        )

    # Even for an approved exchange, completion needs the user's own confirmation.
    if new_status == "completed":
        raise ToolError(
            "Completion requires separate explicit confirmation from the user "
            "that the physical transfer actually happened. Ask the user to confirm it "
            "in the Exchanges tab; you cannot complete it yourself."
        )

    if new_status == "rejected":
        raise ToolError(
            "Rejection records the organisation's decision, so only the user can "
            "record it in the Exchanges tab. Ask the user."
        )

    return _apply_transition(ex, new_status)  # only 'cancelled' (or an invalid move) gets here


# ---------------------------------------- USER-ONLY actions (not AI-callable)
def _run_user_action(fn) -> dict:
    try:
        return fn()
    except ToolError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": redact(f"Action failed: {exc}")}


def _require_confirmed(user_confirmed) -> None:
    # Strict: only the real boolean True counts ("yes", 1, None do not).
    if user_confirmed is not True:
        raise ToolError("Explicit user confirmation is required for this action.")


def _load_exchange(exchange_id) -> dict:
    eid = _opt_int(exchange_id)
    ex = database.get_exchange(eid) if eid else None
    if not ex:
        raise ToolError(f"No exchange with id {eid}.")
    return ex


def confirm_exchange_approval(exchange_id, user_confirmed: bool) -> dict:
    """User confirms the organisation accepted. pending -> approved."""
    def go():
        _require_confirmed(user_confirmed)
        ex = _load_exchange(exchange_id)
        if ex["status"] != "pending":
            raise ToolError(f"Only a pending exchange can be approved (this one is '{ex['status']}').")
        return _apply_transition(ex, "approved")
    return _run_user_action(go)


def confirm_exchange_completion(exchange_id, user_confirmed: bool) -> dict:
    """User confirms the physical transfer happened. approved -> completed (logs impact once)."""
    def go():
        _require_confirmed(user_confirmed)
        ex = _load_exchange(exchange_id)
        if ex["status"] != "approved":
            raise ToolError(
                f"Only an approved exchange can be completed (this one is '{ex['status']}')."
            )
        return _apply_transition(ex, "completed")
    return _run_user_action(go)


def reject_exchange(exchange_id, user_confirmed: bool) -> dict:
    """User records that the organisation declined. pending -> rejected."""
    def go():
        _require_confirmed(user_confirmed)
        ex = _load_exchange(exchange_id)
        return _apply_transition(ex, "rejected")
    return _run_user_action(go)


def cancel_exchange(exchange_id) -> dict:
    """User withdraws a pending or approved request."""
    def go():
        return _apply_transition(_load_exchange(exchange_id), "cancelled")
    return _run_user_action(go)


def _list_records(a, memory):
    kind = _choice(a.get("kind"), ["resources", "exchanges", "impact"], "kind")
    if kind == "resources":
        return {"resources": database.list_resources()}
    if kind == "exchanges":
        return {"exchanges": database.list_exchanges()}
    return database.impact_summary()


_HANDLERS = {
    "analyze_resource": _analyze,
    "save_resource": _save,
    "find_matches": _find_matches,
    "get_reuse_ideas": _ideas,
    "estimate_impact": _impact,
    "create_exchange_request": _create_exchange,
    "update_exchange_status": _update_exchange,
    "list_records": _list_records,
}


def dispatch(name: str, args: dict | None, memory=None) -> dict:
    """Run a tool. Never raises: errors come back as {'error': ...} for the model."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool '{name}'. Available: {', '.join(_HANDLERS)}."}
    try:
        result = handler(args or {}, memory)
    except ToolError as exc:
        return {"error": str(exc)}
    except GeminiError as exc:
        return {"error": f"AI backend problem: {exc}"}
    except Exception as exc:  # noqa: BLE001 - tools must never crash the agent loop
        return {"error": redact(f"Tool '{name}' failed: {exc}")}
    return result if isinstance(result, dict) else {"result": result}


# ------------------------------------------------- declarations for the AI
def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "OBJECT", "properties": props, "required": required or []}


_S = lambda d, **kw: {"type": "STRING", "description": d, **kw}   # noqa: E731
_N = lambda d: {"type": "NUMBER", "description": d}              # noqa: E731
_I = lambda d: {"type": "INTEGER", "description": d}             # noqa: E731

TOOL_DECLARATIONS = [
    {
        "name": "analyze_resource",
        "description": "Identify and classify a described resource: category, material, condition, "
                       "quantity, location and the recommended action (reuse/repair/recycle/dispose). "
                       "Call this first for any new resource description.",
        "parameters": _obj({"description": _S("The user's description of the resource")}, ["description"]),
    },
    {
        "name": "save_resource",
        "description": "Record an analysed resource in the database and get its resource_id. "
                       "Needed before matching by id or creating an exchange request.",
        "parameters": _obj({
            "name": _S("Short item name"),
            "category": _S("Category", enum=K.CATEGORIES),
            "condition": _S("Condition", enum=K.CONDITIONS),
            "quantity": _N("Amount"),
            "unit": _S("Unit", enum=K.UNITS),
            "location": _S("City"),
            "disposition": _S("Recommended action", enum=K.DISPOSITIONS),
            "material": _S("Main material"),
            "notes": _S("Extra notes"),
        }, ["name", "category", "condition", "quantity", "unit"]),
    },
    {
        "name": "find_matches",
        "description": "Rank organisations (schools, NGOs, repairers, recyclers) that could take a resource. "
                       "Pass resource_id of a saved resource, or the category/condition/quantity details directly.",
        "parameters": _obj({
            "resource_id": _I("ID returned by save_resource"),
            "category": _S("Category (if no resource_id)", enum=K.CATEGORIES),
            "condition": _S("Condition (if no resource_id)", enum=K.CONDITIONS),
            "quantity": _N("Amount (if no resource_id)"),
            "unit": _S("Unit (if no resource_id)", enum=K.UNITS),
            "location": _S("City (if no resource_id)"),
            "disposition": _S("Preferred action", enum=K.DISPOSITIONS),
        }),
    },
    {
        "name": "get_reuse_ideas",
        "description": "Get creative, practical reuse/upcycling/recycling ideas for an item.",
        "parameters": _obj({
            "name": _S("Item name"),
            "category": _S("Category", enum=K.CATEGORIES),
            "material": _S("Main material"),
            "condition": _S("Condition", enum=K.CONDITIONS),
        }, ["name", "category"]),
    },
    {
        "name": "estimate_impact",
        "description": "Estimate waste diverted (kg) and CO2e avoided for a chosen action. "
                       "Results are ESTIMATES, never verified measurements.",
        "parameters": _obj({
            "category": _S("Category", enum=K.CATEGORIES),
            "quantity": _N("Amount"),
            "unit": _S("Unit", enum=K.UNITS),
            "action": _S("Action taken", enum=K.DISPOSITIONS),
        }, ["category", "quantity", "unit", "action"]),
    },
    {
        "name": "create_exchange_request",
        "description": "Create a PENDING exchange request offering a saved resource to an organisation. "
                       "Only do this when the user asks to proceed/request the exchange. "
                       "Approval and completion are done by the user in the Exchanges tab, not by you.",
        "parameters": _obj({
            "resource_id": _I("Saved resource ID"),
            "org_id": _I("Organisation ID from find_matches"),
            "message": _S("Short message to the organisation"),
        }, ["resource_id", "org_id"]),
    },
    {
        "name": "update_exchange_status",
        "description": "Cancel an exchange request when the user asks to withdraw it. "
                       "You CANNOT approve, reject or complete exchanges: the user does that in the "
                       "Exchanges tab after confirming the real-world outcome.",
        "parameters": _obj({
            "exchange_id": _I("Exchange ID"),
            "status": _S("New status (only 'cancelled' is allowed for you)", enum=["cancelled"]),
        }, ["exchange_id", "status"]),
    },
    {
        "name": "list_records",
        "description": "List saved resources, exchange requests, or the cumulative (estimated) impact summary.",
        "parameters": _obj({"kind": _S("What to list", enum=["resources", "exchanges", "impact"])}, ["kind"]),
    },
]