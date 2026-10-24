#!/usr/bin/env python3
PATH = "/home/flako1312/jarvis-headless/tests/test_replay_integration.py"
with open(PATH) as f:
    content = f.read()

# Fix: the "    if __name__" got doubled indent from insertion
old = "        if __name__ == \"__main__\":\n        test_name"
new = "    if __name__ == \"__main__\":\n        test_name"

if old in content:
    content = content.replace(old, new, 1)
    with open(PATH, "w") as f:
        f.write(content)
    print("Fixed indentation")
else:
    print("Pattern not found")
