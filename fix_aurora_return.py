#!/usr/bin/env python3
PATH = "/home/flako1312/jarvis-headless/tests/test_replay_integration.py"
with open(PATH) as f:
    content = f.read()

old = '"total_tool_executions": len(all_counters.tool_executions),'
new = '"total_tool_executions": len(all_counters.tool_executions),\n            "total_aurora_log_calls": len(all_counters.aurora_log_calls),'

if old in content and "total_aurora_log_calls" not in content.split("_run_two_turn_test")[1].split("return")[1][:500]:
    content = content.replace(old, new, 1)
    with open(PATH, "w") as f:
        f.write(content)
    print("Fixed: added total_aurora_log_calls to _run_two_turn_test return")
else:
    print("Already present or pattern not found")
