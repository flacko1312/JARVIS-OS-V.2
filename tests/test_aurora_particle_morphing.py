from __future__ import annotations

import numpy as np
import pytest
import threading

from aurora_particles.audio import AudioAnalyzer, pcm16_features
from aurora_particles.controller import MorphController, MorphState
from aurora_particles.quality import QualityManager
from aurora_particles.sampler import ModelPointSampler
from aurora_particles.shapes import SHAPE_FACTORIES, accent_mask
from aurora_particles.state_mapping import STATE_SHAPE_MAP, shape_for_state


def test_quality_presets_have_required_exact_counts():
    assert {k: v.particle_count for k, v in QualityManager.PRESETS.items()} == {
        "low": 4_000, "medium": 10_000, "high": 20_000,
    }


@pytest.mark.parametrize("name", ["core", "brain", "skull", "vortex"])
@pytest.mark.parametrize("count", [4_000, 10_000, 20_000])
def test_procedural_shapes_are_finite_exact_equal_point_sets(name, count):
    points = SHAPE_FACTORIES[name](count)
    assert points.shape == (count, 3)
    assert points.dtype == np.float32
    assert np.isfinite(points).all()
    assert np.max(np.linalg.norm(points, axis=1)) < 1.4


@pytest.mark.parametrize("count", [4_000, 10_000, 20_000])
def test_vortex_accent_mask_marks_nucleus_and_main_rings(count):
    mask = accent_mask("vortex", count)
    assert mask.shape == (count,)
    assert int(np.count_nonzero(mask)) == int(count * .58)
    assert np.all(mask[:int(count * .58)] == 1.0)
    assert np.all(mask[int(count * .58):] == 0.0)


def test_core_is_structured_around_nucleus_rings_and_internal_orbits():
    points = SHAPE_FACTORIES["core"](10_000)
    radii = np.linalg.norm(points, axis=1)
    assert np.count_nonzero(radii < .22) > 1_500
    assert np.count_nonzero((radii > .42) & (radii < .66)) > 3_000
    assert np.max(radii) < .80


def test_vortex_has_compact_nucleus_and_thin_depth_separated_orbits():
    points = SHAPE_FACTORIES["vortex"](10_000)
    radii = np.linalg.norm(points, axis=1)
    assert np.count_nonzero(radii < .10) < 1_000
    assert np.count_nonzero(radii > .60) > 4_000
    assert np.ptp(points[:, 2]) > .75


def test_listening_core_is_smaller_than_brain_and_vortex():
    radii = {
        name: float(np.max(np.linalg.norm(SHAPE_FACTORIES[name](4_000), axis=1)))
        for name in ("core", "brain", "vortex")
    }
    assert radii["core"] < radii["brain"]
    assert radii["core"] < radii["vortex"]


def test_sampler_is_area_weighted_exact_centered_and_cached_safely():
    sampler = ModelPointSampler()
    vertices = [[0, 0, 0], [2, 0, 0], [0, 2, 0], [0, 0, 1]]
    faces = [[0, 1, 2], [0, 1, 3]]
    a = sampler.sample("mesh", vertices, faces, 4096)
    b = sampler.sample("mesh", vertices, faces, 4096)
    assert a.shape == (4096, 3)
    assert np.allclose(a.mean(axis=0), 0, atol=1e-5)
    assert np.max(np.linalg.norm(a, axis=1)) == pytest.approx(1.0)
    b[0] = 99
    assert not np.array_equal(b, sampler.sample("mesh", vertices, faces, 4096))


def test_morph_controller_has_explicit_phases_and_queues_requests():
    c = MorphController(duration=1.0)
    assert c.request("brain")
    assert not c.request("vortex")
    states = []
    for _ in range(12):
        c.update(.1); states.append(c.state)
    assert MorphState.DISSOLVING in states
    assert MorphState.DISPERSED in states
    assert MorphState.REASSEMBLING in states
    assert MorphState.STABILIZING in states
    assert c.target_shape == "vortex"  # queued transition started safely


@pytest.mark.parametrize("state,shape", [
    ("STANDBY", "core"), ("LISTENING", "core"),
    ("THINKING", "brain"), ("PROCESSING", "brain"),
    ("SPEAKING", "vortex"),
])
def test_runtime_state_shape_mapping(state, shape):
    assert STATE_SHAPE_MAP[state] == shape
    assert shape_for_state(state.lower()) == shape


def test_one_hundred_three_shape_cycles_stabilize_without_queue_growth():
    c = MorphController(duration=.01)
    for _ in range(100):
        for shape in ("brain", "vortex", "core"):
            c.request(shape)
            c.update(.25)
    assert c.state is MorphState.STABLE
    assert c.current_shape == "core"
    assert len(c._queue) == 0


def test_pcm_features_detect_low_and_high_frequency_bands():
    sr = 16_000
    t = np.arange(sr // 8) / sr
    low = (np.sin(2*np.pi*100*t)*16000).astype(np.int16).tobytes()
    high = (np.sin(2*np.pi*4000*t)*16000).astype(np.int16).tobytes()
    _, lb = pcm16_features(low, sr)
    _, hb = pcm16_features(high, sr)
    assert lb[0] > lb[2]
    assert hb[2] > hb[0]


def test_audio_analyzer_smooths_and_decays_without_retaining_pcm():
    analyzer = AudioAnalyzer()
    analyzer.set_bands("input", (1, .5, .25))
    before = analyzer.input.copy()
    analyzer.decay(.5)
    assert np.all(analyzer.input < before)
    assert not hasattr(analyzer, "pcm")


def test_existing_audio_forwarder_sends_rms_and_fft_without_new_stream():
    from main import _report_audio_level
    class UI:
        level = None
        bands = None
        def set_input_audio_level(self, value): self.level = value
        def set_input_audio_spectrum(self, *values): self.bands = values
    ui = UI()
    t = np.arange(800) / 16_000
    pcm = (np.sin(2*np.pi*100*t)*12000).astype(np.int16).tobytes()
    _report_audio_level(ui, "input", pcm)
    assert ui.level > 0
    assert len(ui.bands) == 3
    assert ui.bands[0] > ui.bands[2]


def test_shader_uses_same_particle_source_target_and_one_points_draw_call():
    import aurora_particles.widget as widget
    assert "mix(aSource,aTarget" in widget.VERTEX_SHADER
    assert "uDissolve" in widget.VERTEX_SHADER
    assert "aAccentSource" in widget.VERTEX_SHADER
    assert "uAccentColor" in widget.FRAGMENT_SHADER
    source = open(widget.__file__, encoding="utf-8").read()
    assert source.count("glDrawArrays(GL_POINTS") == 1


def test_widget_api_and_raster_fallback():
    from PyQt6.QtWidgets import QApplication
    from aurora_particles.widget import ParticleMorphingCanvas
    app = QApplication.instance() or QApplication([])
    w = ParticleMorphingCanvas(config={"graphics_quality": "low"})
    assert w.renderer_status["particles"] == 4_000
    assert w.morphTo("brain")
    w.set_input_audio_spectrum(.2, .3, .4)
    w.set_output_audio_spectrum(.4, .3, .2)
    w.set_graphics_quality("medium")
    assert w.renderer_status["particles"] == 10_000
    w._gpu_ready = False
    w.resize(400, 320)
    w._paint_fallback()  # context failure remains a non-crashing point cloud
    w.close()
    assert app is not None


def test_microphone_visual_gain_is_input_only():
    from PyQt6.QtWidgets import QApplication
    from aurora_particles.widget import ParticleMorphingCanvas
    app = QApplication.instance() or QApplication([])
    w = ParticleMorphingCanvas(config={"graphics_quality": "low"})
    w.set_input_audio_level(.20)
    w.set_output_audio_level(.20)
    w.set_input_audio_spectrum(.10, .10, .10)
    w.set_output_audio_spectrum(.10, .10, .10)
    assert w._in_level == pytest.approx(.37)
    assert w._out_level == pytest.approx(.20)
    assert np.all(w._audio.input > w._audio.output)
    w.close(); assert app is not None


def test_state_change_starts_only_the_required_morph_once():
    from PyQt6.QtWidgets import QApplication
    from aurora_particles.widget import ParticleMorphingCanvas
    app = QApplication.instance() or QApplication([])
    w = ParticleMorphingCanvas(config={"graphics_quality": "low"})
    calls = []
    original = w.morph_to
    def observed(shape):
        result = original(shape)
        if result: calls.append(shape)
        return result
    w.morph_to = observed
    assert w.set_state("LISTENING") is False  # already core
    assert w.set_state("THINKING") is True
    assert w.set_state("THINKING") is False
    assert calls == ["brain"]
    w.close(); assert app is not None


def test_state_sequence_reaches_core_brain_vortex_core_without_stale_source():
    from PyQt6.QtWidgets import QApplication
    from aurora_particles.widget import ParticleMorphingCanvas
    app = QApplication.instance() or QApplication([])
    w = ParticleMorphingCanvas(config={"graphics_quality": "low"})
    for state, expected in (("THINKING", "brain"), ("SPEAKING", "vortex"), ("LISTENING", "core")):
        w.set_state(state)
        w._morph.update(10.0)
        w._visual_hold_until = 0.0
        w._advance_visual_queue(float("inf"))
        assert w._morph.current_shape == expected
        assert np.array_equal(w._target, w._shapes[expected])
    w.close(); assert app is not None


def test_rapid_logical_timeline_preserves_core_brain_vortex_core_visually(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    import aurora_particles.widget as widget_module
    from aurora_particles.widget import ParticleMorphingCanvas
    app = QApplication.instance() or QApplication([])
    clock = [0.0]
    monkeypatch.setattr(widget_module.time, "perf_counter", lambda: clock[0])
    w = ParticleMorphingCanvas(config={"graphics_quality": "low"})
    w._timer.stop()
    starts = []
    original = w.morph_to
    def observed(shape):
        started = original(shape)
        if started:
            starts.append(shape)
        return started
    w.morph_to = observed

    w.set_state("LISTENING")          # t=0.00, already CORE
    clock[0] = .20; w.set_state("THINKING")
    clock[0] = .35; w.set_state("SPEAKING")
    clock[0] = 2.00; w.set_state("LISTENING")
    assert w.logical_state == "LISTENING"
    assert list(w._visual_queue) == [("SPEAKING", "vortex"), ("LISTENING", "core")]

    for _ in range(45):
        clock[0] += .1
        w._step()

    assert starts == ["brain", "vortex", "core"]
    assert w._morph.current_shape == "core"
    assert w.state == "LISTENING"
    assert not w._visual_queue
    w.close(); assert app is not None


def test_visual_queue_is_bounded_and_deduplicates_rapid_repeats():
    from PyQt6.QtWidgets import QApplication
    from aurora_particles.widget import ParticleMorphingCanvas
    app = QApplication.instance() or QApplication([])
    w = ParticleMorphingCanvas(config={"graphics_quality": "low"})
    w._timer.stop()
    w.set_state("THINKING")
    for _ in range(100):
        w.set_state("SPEAKING")
        w.set_state("SPEAKING")
        w.set_state("LISTENING")
    assert len(w._visual_queue) <= 4
    assert all(a[1] != b[1] for a, b in zip(w._visual_queue, list(w._visual_queue)[1:]))
    w.close(); assert app is not None


def test_shader_caps_point_size_and_accent_saturation():
    import aurora_particles.widget as widget
    assert "min(1.65" in widget.VERTEX_SHADER
    assert "vAccent*.72" in widget.FRAGMENT_SHADER


def test_visual_lifecycle_logs_logical_enqueue_start_and_complete(caplog, monkeypatch):
    from PyQt6.QtWidgets import QApplication
    import aurora_particles.widget as widget_module
    from aurora_particles.widget import ParticleMorphingCanvas
    app = QApplication.instance() or QApplication([])
    clock = [0.0]
    monkeypatch.setattr(widget_module.time, "perf_counter", lambda: clock[0])
    w = ParticleMorphingCanvas(config={"graphics_quality": "low"})
    w._timer.stop()
    w._morph.duration = .05
    with caplog.at_level("INFO", logger="jarvis.aurora_particles"):
        w.set_state("THINKING")
        w.set_state("SPEAKING")
        clock[0] = .10
        w._step()
    log = caplog.text
    assert "PARTICLE_STATE logical THINKING" in log
    assert "PARTICLE_VISUAL enqueue vortex" in log
    assert "PARTICLE_MORPH core -> brain" in log
    assert "PARTICLE_MORPH complete shape=brain" in log
    w.close(); assert app is not None


def test_repeated_speaking_does_not_restart_vortex_morph():
    from PyQt6.QtWidgets import QApplication
    from aurora_particles.widget import ParticleMorphingCanvas
    app = QApplication.instance() or QApplication([])
    w = ParticleMorphingCanvas(config={"graphics_quality": "low"})
    assert w.set_state("SPEAKING") is True
    elapsed = w._morph._elapsed
    assert w.set_state("SPEAKING") is False
    assert w._morph.target_shape == "vortex"
    assert w._morph._elapsed == elapsed
    w.close(); assert app is not None


def test_audio_facade_uses_thread_safe_signal_boundary_from_worker():
    from ui import JarvisUI
    emitted = []
    class Signal:
        def __init__(self, name): self.name = name
        def emit(self, *values): emitted.append((self.name, values, threading.get_ident()))
    class Window:
        _input_audio_sig = Signal("input_rms")
        _output_audio_sig = Signal("output_rms")
        _input_fft_sig = Signal("input_fft")
        _output_fft_sig = Signal("output_fft")
    facade = JarvisUI.__new__(JarvisUI); facade._win = Window()
    worker_id = []
    def worker():
        worker_id.append(threading.get_ident())
        facade.set_input_audio_level(.4); facade.set_input_audio_spectrum(.1, .2, .3)
        facade.set_output_audio_level(.5); facade.set_output_audio_spectrum(.3, .2, .1)
    thread = threading.Thread(target=worker); thread.start(); thread.join()
    assert [item[0] for item in emitted] == ["input_rms", "input_fft", "output_rms", "output_fft"]
    assert all(item[2] == worker_id[0] for item in emitted)
