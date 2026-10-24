#!/usr/bin/env python3
"""Patch: Tool guard fail-closed + semantic tool dedup."""

PATH = "/home/flako1312/jarvis-headless/main.py"
with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

changes = 0

# ═══════════════════════════════════════════════════════════════
# FIX 1: Tool guard fail-closed using _input_validated
# ═══════════════════════════════════════════════════════════════

old_guard = '''                            current_input = " ".join(in_buf).strip()
                            if in_buf and not _is_semantic_transcript(current_input):
                                logger.info(
                                    "VOICE_INPUT ignored reason=non_semantic_transcript turn_id=%s text=%r",
                                    live_turn_id, current_input[:80],
                                )
                                fn_responses = [
                                    types.FunctionResponse(
                                        id=fc.id,
                                        name=getattr(fc, "name", "tool"),
                                        response={"result": "Non-semantic input; tool call skipped."},
                                    )
                                    for fc in function_calls
                                ]
                            else:'''

new_guard = '''                            if not _input_validated:
                                current_input = " ".join(in_buf).strip()
                                logger.info(
                                    "TOOL_CALL rejected reason=no_valid_semantic_input turn_id=%s text=%r tools=%s",
                                    live_turn_id, current_input[:80],
                                    [getattr(fc, "name", "?") for fc in function_calls],
                                )
                                fn_responses = [
                                    types.FunctionResponse(
                                        id=fc.id,
                                        name=getattr(fc, "name", "tool"),
                                        response={"result": "No valid semantic input; tool call rejected."},
                                    )
                                    for fc in function_calls
                                ]
                            else:'''

if old_guard in content:
    content = content.replace(old_guard, new_guard, 1)
    changes += 1
    print("  [1] Tool guard changed to fail-closed (_input_validated)")
else:
    print("  [1] SKIP - tool guard pattern not found")

# ═══════════════════════════════════════════════════════════════
# FIX 2: Semantic tool dedup (name + canonical args, not ID)
# ═══════════════════════════════════════════════════════════════

old_dedup_sig = '''                                    sig = f"{getattr(fc, 'name', '')}:{getattr(fc, 'id', '')}"
                                    if sig in self._turn_tool_signatures:'''

new_dedup_sig = '''                                    import json as _json
                                    _fc_args = getattr(fc, "args", {}) or {}
                                    sig = f"{getattr(fc, 'name', '')}:{_json.dumps(_fc_args, sort_keys=True, default=str)}"
                                    if sig in self._turn_tool_signatures:'''

if old_dedup_sig in content:
    content = content.replace(old_dedup_sig, new_dedup_sig, 1)
    changes += 1
    print("  [2a] Dedup signature changed to name+canonical_args")
else:
    print("  [2a] SKIP - dedup sig pattern not found")

# Also fix the second reference to sig (in the merge loop)
old_dedup_merge = '''                                    for fc in function_calls:
                                        sig = f"{getattr(fc, 'name', '')}:{getattr(fc, 'id', '')}"
                                        if any(getattr(d, 'id', None) == fc.id for d in dup_responses):'''

new_dedup_merge = '''                                    for fc in function_calls:
                                        if any(getattr(d, 'id', None) == fc.id for d in dup_responses):'''

if old_dedup_merge in content:
    content = content.replace(old_dedup_merge, new_dedup_merge, 1)
    changes += 1
    print("  [2b] Removed stale sig rebuild in merge loop")
else:
    print("  [2b] SKIP - dedup merge pattern not found")

# Also update the add to signatures set
old_dedup_add = '''                                        self._turn_tool_signatures.add(sig)
                                        filtered_calls.append(fc)'''

# This should stay as-is since sig is already computed above.
# Just verify it's there.
if old_dedup_add in content:
    print("  [2c] OK - sig add already correct")
else:
    print("  [2c] SKIP - sig add not found")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\nPatch applied: {changes} changes")
