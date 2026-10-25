"""Repeatable local benchmark for the AURORA neural renderer.

This opens one small native OpenGL widget, measures frame swaps and process CPU/
RSS, then performs 100 accelerated four-state cycles. It does not open audio
devices, start Gemini or execute tools.
"""
from __future__ import annotations

import json
import gc
from pathlib import Path
import statistics
import sys
import time

import psutil
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aurora_particles.widget import ParticleMorphingCanvas


def run_window(app, widget, seconds: float, active: bool) -> dict:
    stamps = []
    pulse = QTimer()
    if active:
        pulse.timeout.connect(lambda: (
            widget.set_input_audio_spectrum(.35, .22, .16),
            widget.set_input_audio_level(.28),
        ))
        pulse.start(30)
    def record_frame():
        stamps.append(time.perf_counter())
    widget.frameSwapped.connect(record_frame)
    proc = psutil.Process()
    cpu0 = proc.cpu_times(); rss0 = proc.memory_info().rss; start = time.perf_counter()
    loop = QEventLoop(); QTimer.singleShot(int(seconds * 1000), loop.quit); loop.exec()
    elapsed = time.perf_counter() - start; cpu1 = proc.cpu_times(); rss1 = proc.memory_info().rss
    pulse.stop(); widget.frameSwapped.disconnect(record_frame)
    intervals = [(b-a)*1000 for a, b in zip(stamps, stamps[1:])]
    p99 = sorted(intervals)[max(0, int(len(intervals)*.99)-1)] if intervals else 0.0
    return {
        "frames": len(stamps), "average_fps": round(max(0, len(stamps)-1)/elapsed, 2),
        "mean_frame_ms": round(statistics.mean(intervals), 2) if intervals else 0.0,
        "one_percent_low_fps": round(1000/p99, 2) if p99 else 0.0,
        "process_cpu_percent_one_core": round(((cpu1.user+cpu1.system)-(cpu0.user+cpu0.system))/elapsed*100, 2),
        "rss_delta_mib": round((rss1-rss0)/(1024*1024), 3),
    }


def main():
    app = QApplication.instance() or QApplication([])
    widget = ParticleMorphingCanvas(config={"graphics_quality": "low"})
    widget.resize(720, 560); widget.show()
    warm = QEventLoop(); QTimer.singleShot(500, warm.quit); warm.exec()
    results = {"renderer": widget.renderer_status, "profiles": {}}
    for quality in ("low", "medium", "high"):
        widget.set_graphics_quality(quality)
        results["profiles"][quality] = {
            "idle": run_window(app, widget, 1.5, False),
        }
        widget.set_state("SPEAKING")
        results["profiles"][quality]["state_audio"] = run_window(app, widget, 2.6, True)

    proc = psutil.Process()
    def cycles(total):
      for _ in range(total):
        for state in ("LISTENING", "PROCESSING", "SPEAKING", "STANDBY"):
            widget.set_state(state)
            for _step in range(14):
                widget._state_controller.update(.1)
            widget.update(); app.processEvents()
    cycles(10)  # exclude one-time driver/buffer allocation from leak window
    gc.collect(); before = proc.memory_info().rss
    cycles(100)
    gc.collect(); app.processEvents(); after = proc.memory_info().rss
    results["stress_100_cycles"] = {
        "rss_before_mib": round(before/(1024*1024), 3),
        "rss_after_mib": round(after/(1024*1024), 3),
        "rss_delta_mib": round((after-before)/(1024*1024), 3),
        "final": widget.renderer_status,
    }
    widget.close()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
