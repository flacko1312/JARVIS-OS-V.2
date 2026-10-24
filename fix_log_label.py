#!/usr/bin/env python3
PATH = "/home/flako1312/jarvis-headless/tests/test_replay_integration.py"
with open(PATH) as f:
    content = f.read()

# Update instrumentation to catch JARVIS: instead of AURORA:
old = 'if text.startswith("AURORA:")'
new = 'if text.startswith("JARVIS:") or text.startswith("AURORA:")'

if old in content:
    content = content.replace(old, new, 1)
    with open(PATH, "w") as f:
        f.write(content)
    print("Fixed: instrumentation catches both JARVIS: and AURORA: log labels")
else:
    print("Pattern not found")
