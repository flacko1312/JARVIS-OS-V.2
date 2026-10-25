"""Capture reproducible native-framebuffer evidence for AURORA particles.

This opens only the particle widget. It does not start Gemini, audio devices,
the full HUD, or any JARVIS tool. Output directory is fixed beneath the existing
pre-work restore checkpoint unless an explicit CLI directory is supplied.
"""
from __future__ import annotations

from pathlib import Path
import sys
import time

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aurora_particles.widget import ParticleMorphingCanvas


DEFAULT_OUTPUT = Path(
    r"C:\JARVIS_CHECKPOINTS\particle-morphing-prework-2026-10-25-b759b3f"
) / "timing-definition-validation"


def wait(app: QApplication, milliseconds: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()
    app.processEvents()


def save(widget: ParticleMorphingCanvas, path: Path) -> None:
    widget.update()
    QApplication.processEvents()
    image = widget.grabFramebuffer()
    if image.isNull() or not image.save(str(path), "PNG"):
        raise RuntimeError(f"Could not save framebuffer: {path}")


def wait_mode(app: QApplication, widget: ParticleMorphingCanvas, mode: str,
              timeout_ms: int = 4000) -> None:
    deadline = time.perf_counter() + timeout_ms / 1000.0
    while time.perf_counter() < deadline:
        if widget._state_controller.current == mode and widget._state_controller.stable:
            return
        wait(app, 30)
    raise RuntimeError(f"Visual mode did not stabilize: {mode}; {widget.renderer_status}")


def main() -> None:
    output = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    widget = ParticleMorphingCanvas(
        config={"graphics_quality": "medium"},
        palette_provider=lambda: ("#ff365d", "#ff58c7"),
    )
    widget.resize(760, 620)
    widget.show()
    wait(app, 650)

    started = time.perf_counter()
    save(widget, output / "01_standby_stable.png")
    standby_sequence = output / "standby_sequence"
    standby_sequence.mkdir(exist_ok=True)
    for frame in range(6):
        if frame: wait(app, 1_000)
        save(widget, standby_sequence / f"{frame + 1:02d}.png")

    widget.set_state("LISTENING")
    wait_mode(app, widget, "listening")
    widget.set_input_audio_level(.10)
    widget.set_input_audio_spectrum(.08, .06, .04)
    wait(app, 100)
    save(widget, output / "02_listening_low_audio.png")
    widget.set_input_audio_level(.48)
    widget.set_input_audio_spectrum(.42, .32, .28)
    wait(app, 100)
    save(widget, output / "03_listening_high_audio.png")

    widget.set_state("THINKING")
    wait(app, 520)
    save(widget, output / "04_listening_to_processing.png")
    wait(app, 650)
    wait_mode(app, widget, "processing")
    save(widget, output / "05_processing_stable.png")

    widget.set_state("SPEAKING")
    widget.set_output_audio_level(.28)
    widget.set_output_audio_spectrum(.30, .20, .18)
    wait(app, 520)
    save(widget, output / "06_processing_to_speaking.png")
    wait(app, 650)
    wait_mode(app, widget, "speaking")
    save(widget, output / "07_speaking_audio.png")
    speaking_sequence = output / "speaking_sequence"
    speaking_sequence.mkdir(exist_ok=True)
    phrase_envelope = (
        (.16,.14,.10,.08),(.38,.32,.24,.18),(.25,.18,.30,.16),
        (.47,.40,.22,.26),(.20,.15,.18,.12),(.34,.26,.28,.20),
    )
    for frame,(rms,bass,mid,high) in enumerate(phrase_envelope,1):
        widget.set_output_audio_level(rms)
        widget.set_output_audio_spectrum(bass,mid,high)
        wait(app, 360)
        save(widget, speaking_sequence / f"{frame:02d}.png")

    widget.set_state("STANDBY")
    wait(app, 520)
    save(widget, output / "08_speaking_to_standby.png")
    wait(app, 650)
    wait_mode(app, widget, "standby")
    save(widget, output / "09_standby_returned.png")

    elapsed = time.perf_counter() - started
    (output / "capture-summary.txt").write_text(
        "AURORA native framebuffer capture\n"
        f"elapsed_seconds={elapsed:.3f}\n"
        f"transition_duration_seconds={widget._state_controller.duration:.3f}\n"
        f"processing_hold_seconds=0.420\n"
        "standby_sequence_frames=6 interval_ms=1000\n"
        "speaking_sequence_frames=6 interval_ms=360 synthetic_audio=true\n"
        f"renderer={widget.renderer_status}\n",
        encoding="utf-8",
    )
    widget.close()
    print(output)


if __name__ == "__main__":
    main()
