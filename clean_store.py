#!/usr/bin/env python3
"""Clean contaminated entries from conversation store.

Removes ONLY the known entries from the physical test:
- turn_id f153c7166cd646548e54914d2ac92a06 (interrupted replay source)
- turn_id 94edf0404fb447f09e4e8ce071475875 (replay that should have been blocked)
- turn_id 23a028331dc745e5ac4cd15156f45d31 (Para/Disculpa control pair)
"""

import json

PATH = "/home/flako1312/jarvis-headless/memory/conversation_state_headless.json"

CONTAMINATED_TURN_IDS = {
    "f153c7166cd646548e54914d2ac92a06",  # interrupted source turn (assistant partial)
    "94edf0404fb447f09e4e8ce071475875",  # replay turn (should not have persisted)
    "23a028331dc745e5ac4cd15156f45d31",  # "Para" / "Disculpa" control pair
}

with open(PATH) as f:
    data = json.load(f)

original_count = len(data.get("recent_turns", []))

# Remove contaminated entries
cleaned_turns = [
    t for t in data.get("recent_turns", [])
    if t.get("turn_id") not in CONTAMINATED_TURN_IDS
]

removed = original_count - len(cleaned_turns)
data["recent_turns"] = cleaned_turns

# Also clean from recent_tool_results if any
original_tools = len(data.get("recent_tool_results", []))
cleaned_tools = [
    t for t in data.get("recent_tool_results", [])
    if t.get("turn_id") not in CONTAMINATED_TURN_IDS
]
tools_removed = original_tools - len(cleaned_tools)
data["recent_tool_results"] = cleaned_tools

with open(PATH, "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Removed {removed} turn entries, {tools_removed} tool entries")
print(f"Remaining turns: {len(cleaned_turns)}")

# Verify
for i, t in enumerate(cleaned_turns):
    role = t.get("role", "?")
    text = t.get("text", "")[:80]
    tid = t.get("turn_id", "?")[:12]
    print(f"  [{i}] {role}: {text!r}  tid={tid}")
