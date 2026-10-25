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
    widget.set_state("LISTENING")
    save(widget, output / "01_core_stable.png")
    widget.set_input_audio_level(.34)
    widget.set_input_audio_spectrum(.34, .22, .17)
    wait(app, 80)
    save(widget, output / "02_core_audio.png")

    widget.set_state("THINKING")
    wait(app, 520)
    save(widget, output / "03_core_to_brain.png")
    wait(app, 650)
    save(widget, output / "04_brain_stable.png")

    widget.set_state("SPEAKING")
    widget.set_output_audio_level(.28)
    widget.set_output_audio_spectrum(.30, .20, .18)
    wait(app, 520)
    save(widget, output / "05_brain_to_vortex.png")
    wait(app, 650)
    save(widget, output / "06_vortex_stable_audio.png")

    widget.set_state("LISTENING")
    wait(app, 520)
    save(widget, output / "07_vortex_to_core.png")
    wait(app, 650)
    save(widget, output / "08_core_returned.png")

    elapsed = time.perf_counter() - started
    (output / "capture-summary.txt").write_text(
        "AURORA native framebuffer capture\n"
        f"elapsed_seconds={elapsed:.3f}\n"
        f"morph_duration_seconds={widget._morph.duration:.3f}\n"
        f"brain_min_hold_seconds={widget._brain_min_hold:.3f}\n"
        f"renderer={widget.renderer_status}\n",
        encoding="utf-8",
    )
    widget.close()
    print(output)


if __name__ == "__main__":
    main()
