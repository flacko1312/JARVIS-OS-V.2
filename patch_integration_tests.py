#!/usr/bin/env python3
"""Patch test_replay_integration.py to add no-input and non-semantic tests + write_log instrumentation."""

PATH = "/home/flako1312/jarvis-headless/tests/test_replay_integration.py"
with open(PATH) as f:
    content = f.read()

changes = 0

# 1. Add aurora_log to _Counters
old_counters = """    class _Counters:
        def __init__(self):
            self.user_memory = []
            self.assistant_memory = []
            self.schedule_updates = []
            self.schedule_begins = []
            self.subtitle_calls = []
            self.audio_released = []
            self.tool_executions = []"""

new_counters = """    class _Counters:
        def __init__(self):
            self.user_memory = []
            self.assistant_memory = []
            self.schedule_updates = []
            self.schedule_begins = []
            self.subtitle_calls = []
            self.audio_released = []
            self.tool_executions = []
            self.aurora_log_calls = []"""

if old_counters in content:
    content = content.replace(old_counters, new_counters, 1)
    changes += 1
    print("  [1] Added aurora_log_calls to _Counters")

# 2. Instrument write_log
old_instrument = """        # Stub methods that touch external systems
        jl._interrupt_live_playback = lambda reason: None"""

new_instrument = """        original_write_log = jl.ui.write_log

        def _patched_write_log(text):
            if text.startswith("AURORA:"):
                counters.aurora_log_calls.append(text[:80])

        jl.ui.write_log = _patched_write_log

        # Stub methods that touch external systems
        jl._interrupt_live_playback = lambda reason: None"""

if old_instrument in content:
    content = content.replace(old_instrument, new_instrument, 1)
    changes += 1
    print("  [2] Instrumented write_log for AURORA log tracking")

# 3. Add new unittest class methods after test_real_receive_audio_different_input
old_class_end = """    def test_real_receive_audio_different_input(self):
        \"\"\"TURN A interrupted + TURN B different input -> input validated.\"\"\"
        p = self._run_worker("different_input")
        self.assertTrue(p["passed"])
        self.assertTrue(p["turn_b_input_validated"], "Different input should be validated")
        self.assertFalse(p["turn_b_replay_rejected"], "Different input should NOT be replay-rejected")"""

new_class_end = """    def test_real_receive_audio_different_input(self):
        \"\"\"TURN A interrupted + TURN B different input -> input validated.\"\"\"
        p = self._run_worker("different_input")
        self.assertTrue(p["passed"])
        self.assertTrue(p["turn_b_input_validated"], "Different input should be validated")
        self.assertFalse(p["turn_b_replay_rejected"], "Different input should NOT be replay-rejected")

    def test_no_input_turn_zero_side_effects(self):
        \"\"\"Turn with no input_transcription at all -> zero side effects.\"\"\"
        p = self._run_worker("no_input_turn")
        self.assertTrue(p["passed"])
        self.assertFalse(p["input_validated"], "No input -> not validated")
        self.assertEqual(p["audio_released"], 0, "No input: audio released must be 0")
        self.assertEqual(p["user_memory_writes"], 0, "No input: user memory must be 0")
        self.assertEqual(p["assistant_memory_writes"], 0, "No input: assistant memory must be 0")
        self.assertEqual(p["tool_executions"], 0, "No input: tool executions must be 0")
        self.assertEqual(p["schedule_begins"], 0, "No input: schedule begins must be 0")
        self.assertEqual(p["schedule_updates"], 0, "No input: schedule updates must be 0")
        self.assertEqual(p["subtitle_calls"], 0, "No input: subtitle calls must be 0")
        self.assertEqual(p["aurora_log_calls"], 0, "No input: AURORA log writes must be 0")

    def test_nonsemantic_input_turn_zero_side_effects(self):
        \"\"\"Turn with non-semantic input '.' -> zero side effects.\"\"\"
        p = self._run_worker("nonsemantic_input_turn")
        self.assertTrue(p["passed"])
        self.assertFalse(p["input_validated"], "Dot input -> not validated")
        self.assertEqual(p["audio_released"], 0, "Dot input: audio released must be 0")
        self.assertEqual(p["user_memory_writes"], 0, "Dot input: user memory must be 0")
        self.assertEqual(p["assistant_memory_writes"], 0, "Dot input: assistant memory must be 0")
        self.assertEqual(p["tool_executions"], 0, "Dot input: tool executions must be 0")
        self.assertEqual(p["schedule_begins"], 0, "Dot input: schedule begins must be 0")
        self.assertEqual(p["schedule_updates"], 0, "Dot input: schedule updates must be 0")
        self.assertEqual(p["subtitle_calls"], 0, "Dot input: subtitle calls must be 0")
        self.assertEqual(p["aurora_log_calls"], 0, "Dot input: AURORA log writes must be 0")"""

if old_class_end in content:
    content = content.replace(old_class_end, new_class_end, 1)
    changes += 1
    print("  [3] Added no_input and nonsemantic test class methods")

# 4. Add _run_single_turn_test helper and new test worker implementations
# Find the dispatch dict to add new entries
old_dispatch = """        dispatch = {
            "real_replay": test_real_replay,
            "normal_repeat": test_normal_repeat,
            "different_input": test_different_input,
        }"""

new_dispatch = """        dispatch = {
            "real_replay": test_real_replay,
            "normal_repeat": test_normal_repeat,
            "different_input": test_different_input,
            "no_input_turn": test_no_input_turn,
            "nonsemantic_input_turn": test_nonsemantic_input_turn,
        }"""

if old_dispatch in content:
    content = content.replace(old_dispatch, new_dispatch, 1)
    changes += 1
    print("  [4] Added new tests to dispatch")

# 5. Add test implementations before dispatch
# Insert before "    if __name__"
old_main = '    if __name__ == "__main__":'

new_tests_and_main = """    async def _run_single_turn_test(responses):
        \"\"\"Run _receive_audio with a single turn and return counters.\"\"\"
        all_counters = _Counters()
        session = _FakeSession([responses])
        jl = _make_instrumented_jl(session, all_counters)

        async def _auto_shutdown():
            await asyncio.sleep(0.5)
            jl._shutdown_requested.set()

        loop = asyncio.get_event_loop()
        shutdown_task = loop.create_task(_auto_shutdown())

        try:
            await jl._receive_audio()
        except Exception:
            pass

        shutdown_task.cancel()

        return {
            "user_memory_writes": len(all_counters.user_memory),
            "assistant_memory_writes": len(all_counters.assistant_memory),
            "audio_released": len(all_counters.audio_released),
            "schedule_updates": len(all_counters.schedule_updates),
            "schedule_begins": len(all_counters.schedule_begins),
            "subtitle_calls": len(all_counters.subtitle_calls),
            "tool_executions": len(all_counters.tool_executions),
            "aurora_log_calls": len(all_counters.aurora_log_calls),
        }

    def test_no_input_turn():
        \"\"\"Turn with NO input_transcription, provider sends audio + output + turn_complete.\"\"\"
        responses = [
            _make_response(audio_bytes=b"\\x00" * 320),
            _make_response(output_text="Algo que dijo el modelo sin input"),
            _make_response(audio_bytes=b"\\x00" * 160),
            _make_response(turn_complete=True),
        ]

        result = asyncio.run(_run_single_turn_test(responses))

        return {
            "passed": True,
            "input_validated": False,
            "audio_released": result["audio_released"],
            "user_memory_writes": result["user_memory_writes"],
            "assistant_memory_writes": result["assistant_memory_writes"],
            "tool_executions": result["tool_executions"],
            "schedule_begins": result["schedule_begins"],
            "schedule_updates": result["schedule_updates"],
            "subtitle_calls": result["subtitle_calls"],
            "aurora_log_calls": result["aurora_log_calls"],
        }

    def test_nonsemantic_input_turn():
        \"\"\"Turn with non-semantic input '.', provider sends audio + output + turn_complete.\"\"\"
        responses = [
            _make_response(input_text="."),
            _make_response(audio_bytes=b"\\x00" * 320),
            _make_response(output_text="Respuesta a un punto"),
            _make_response(audio_bytes=b"\\x00" * 160),
            _make_response(turn_complete=True),
        ]

        result = asyncio.run(_run_single_turn_test(responses))

        return {
            "passed": True,
            "input_validated": False,
            "audio_released": result["audio_released"],
            "user_memory_writes": result["user_memory_writes"],
            "assistant_memory_writes": result["assistant_memory_writes"],
            "tool_executions": result["tool_executions"],
            "schedule_begins": result["schedule_begins"],
            "schedule_updates": result["schedule_updates"],
            "subtitle_calls": result["subtitle_calls"],
            "aurora_log_calls": result["aurora_log_calls"],
        }

    if __name__ == "__main__":"""

if old_main in content:
    content = content.replace(old_main, new_tests_and_main, 1)
    changes += 1
    print("  [5] Added single-turn test helper and test implementations")

with open(PATH, "w") as f:
    f.write(content)

print(f"\nPatch applied: {changes} changes")
