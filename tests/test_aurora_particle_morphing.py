from __future__ import annotations

import threading

import numpy as np
import pytest

from aurora_particles.audio import AudioAnalyzer, pcm16_features
from aurora_particles.neural_graph import build_neural_graph
from aurora_particles.neural_morph import reference_morph_positions
from aurora_particles.neural_state import MODE_INDEX, NeuralStateController
from aurora_particles.quality import QualityManager
from aurora_particles.sampler import ModelPointSampler


def test_quality_presets_match_bounded_neural_budget():
    assert {k: (v.particle_count, v.edge_count) for k, v in QualityManager.PRESETS.items()} == {
        "low": (450, 2_000), "medium": (800, 3_200), "high": (1_200, 5_500),
    }
    assert QualityManager().current.name == "medium"


def test_quality_auto_degrades_only_after_sustained_low_fps():
    manager = QualityManager("high")
    for _ in range(29):
        assert manager.observe_frame(.1) is None
    assert manager.observe_frame(.1) == "medium"
    manager.set("medium")
    for _ in range(100):
        assert manager.observe_frame(1/60) is None
    assert manager.current.name == "medium"


@pytest.mark.parametrize("quality", ["low", "medium", "high"])
def test_graph_has_exact_finite_pooled_buffers(quality):
    preset = QualityManager.PRESETS[quality]
    graph = build_neural_graph(preset.particle_count, preset.edge_count)
    assert graph.nodes.shape == (preset.particle_count, 3)
    assert graph.edge_vertices.shape == (preset.edge_count * 2, 3)
    assert graph.node_seed.shape == (preset.particle_count,)
    assert graph.edge_path.shape == graph.edge_layer.shape == (preset.edge_count * 2,)
    assert sum(graph.filament_segment_counts) == preset.edge_count
    assert sum(graph.layer_segment_counts) == preset.edge_count
    assert graph.nodes.dtype == graph.edge_vertices.dtype == np.float32
    assert np.isfinite(graph.nodes).all() and np.isfinite(graph.edge_vertices).all()


def test_graph_is_deterministic_irregular_and_not_a_spherical_shell():
    first = build_neural_graph(800, 3_200)
    second = build_neural_graph(800, 3_200)
    assert np.array_equal(first.nodes, second.nodes)
    radii = np.linalg.norm(first.nodes, axis=1)
    assert np.std(radii) > .16
    assert np.ptp(first.nodes[:, 2]) < max(np.ptp(first.nodes[:, 0]), np.ptp(first.nodes[:, 1]))
    assert abs(float(np.ptp(first.nodes[:, 1]) - np.ptp(first.nodes[:, 0]))) < .20
    assert np.count_nonzero(radii < .20) > 45


def test_filaments_are_long_continuous_cubic_paths_in_three_layers():
    graph = build_neural_graph(450, 2_000)
    assert graph.filament_count == len(graph.filament_segment_counts)
    assert graph.filament_count >= 42
    assert set(np.unique(graph.edge_layer)) == {0.0, 1.0, 2.0}
    offset = 0
    for segment_count in graph.filament_segment_counts:
        points = graph.edge_vertices[offset:offset + segment_count * 2]
        route = graph.edge_path[offset:offset + segment_count * 2]
        assert np.allclose(points[1:-1:2], points[2::2])
        assert route[0] == pytest.approx(0.0)
        assert route[-1] == pytest.approx(1.0)
        offset += segment_count * 2
    assert offset == len(graph.edge_vertices)


def test_medium_uses_hierarchical_branches_instead_of_radial_only_routes():
    graph = build_neural_graph(800, 3_200)
    assert graph.layer_filament_counts == (42, 110, 280)
    starts = [[], [], []]
    offset = 0
    filament = 0
    for layer, count in enumerate(graph.layer_filament_counts):
        for _ in range(count):
            starts[layer].append(float(np.linalg.norm(graph.edge_vertices[offset, :2])))
            offset += graph.filament_segment_counts[filament] * 2
            filament += 1
    assert np.quantile(starts[0], .9) < .06
    assert np.median(starts[1]) > .18
    assert np.median(starts[2]) > .20


def test_state_controller_inertially_blends_without_geometry_swap():
    controller = NeuralStateController()
    assert controller.request("listening")
    controller.update(.20)
    assert 0 < controller.weights[MODE_INDEX["listening"]] < 1
    assert 0 < controller.weights[MODE_INDEX["standby"]] < 1
    assert np.sum(controller.weights) == pytest.approx(1.0)


def test_state_controller_preserves_processing_in_fast_full_cycle():
    controller = NeuralStateController()
    starts = []
    assert controller.request("listening")
    controller.request("processing")
    controller.request("speaking")
    controller.request("standby")
    for _ in range(80):
        before = controller.target
        controller.update(.1)
        if controller.target != before:
            starts.append(controller.target)
    assert starts == ["processing", "speaking", "standby"]
    assert controller.current == "standby"
    assert controller.stable
    assert not controller._queue


def test_state_queue_is_bounded_and_deduplicates_repeats():
    controller = NeuralStateController()
    controller.request("listening")
    for _ in range(100):
        controller.request("processing")
        controller.request("processing")
        controller.request("speaking")
        controller.request("standby")
    assert len(controller._queue) <= 4
    assert all(a != b for a, b in zip(controller._queue, list(controller._queue)[1:]))


def test_transition_durations_remain_within_requested_inertia_range():
    controller = NeuralStateController()
    for current, target in (("standby", "listening"), ("listening", "processing"),
                            ("processing", "speaking"), ("speaking", "standby")):
        controller.current = current; controller.target = current; controller.progress = 1.0
        controller.hold_remaining = 0.0; controller.weights[:] = 0; controller.weights[MODE_INDEX[current]] = 1
        assert controller.request(target)
        assert .5 <= controller.duration <= 1.2


def test_shader_separates_rms_bass_mid_high_and_directed_impulses():
    import aurora_particles.widget as widget
    assert "rms=uAudio.x,bass=uAudio.y,mid=uAudio.z,high=uAudio.w" in widget.DEFORM_GLSL
    assert "listenPull" in widget.DEFORM_GLSL and "speakOpen" in widget.DEFORM_GLSL
    assert "branchDrift" in widget.DEFORM_GLSL and "idleMorph" in widget.DEFORM_GLSL
    assert "petal" in widget.DEFORM_GLSL and "attention" in widget.DEFORM_GLSL
    assert "1.0-phase" in widget.EDGE_FRAGMENT_SHADER
    assert "pulse" in widget.EDGE_FRAGMENT_SHADER
    assert "uGlowPass" in widget.EDGE_FRAGMENT_SHADER
    assert "glDrawArrays(GL_LINES" in open(widget.__file__, encoding="utf-8").read()
    assert "glDrawArrays(GL_POINTS" in open(widget.__file__, encoding="utf-8").read()


def test_standby_morph_changes_silhouette_without_audio():
    graph = build_neural_graph(800, 3_200)
    start = reference_morph_positions(graph.nodes, graph.node_role, (1, 0, 0, 0), time_seconds=0.0)
    later = reference_morph_positions(graph.nodes, graph.node_role, (1, 0, 0, 0), time_seconds=7.0)
    displacement = np.linalg.norm(later[:, :2] - start[:, :2], axis=1)
    start_span = np.ptp(start[:, :2], axis=0)
    later_span = np.ptp(later[:, :2], axis=0)
    assert np.mean(displacement) > .018
    assert np.max(np.abs(later_span - start_span)) > .025


def test_state_gestures_change_global_shape_not_only_energy():
    graph = build_neural_graph(800, 3_200)
    audio = (.42, .35, .25, .18)
    states = {
        "standby": (1, 0, 0, 0), "listening": (0, 1, 0, 0),
        "processing": (0, 0, 1, 0), "speaking": (0, 0, 0, 1),
    }
    shapes = {name: reference_morph_positions(graph.nodes, graph.node_role, weights, audio, time_seconds=4.0)
              for name, weights in states.items()}
    radial = {name: np.linalg.norm(points[:, :2], axis=1) for name, points in shapes.items()}
    spans = {name: np.ptp(points[:, :2], axis=0) for name, points in shapes.items()}
    assert np.quantile(radial["listening"], .90) < np.quantile(radial["standby"], .90) * .94
    assert np.quantile(radial["speaking"], .90) > np.quantile(radial["standby"], .90) * 1.28
    assert np.linalg.norm(spans["processing"] - spans["standby"]) > .10
    assert np.linalg.norm(spans["speaking"] - spans["listening"]) > .55


def test_sampler_remains_available_for_future_model_sources():
    sampler = ModelPointSampler()
    vertices = [[0, 0, 0], [2, 0, 0], [0, 2, 0], [0, 0, 1]]
    faces = [[0, 1, 2], [0, 1, 3]]
    points = sampler.sample("mesh", vertices, faces, 512)
    assert points.shape == (512, 3)
    assert np.allclose(points.mean(axis=0), 0, atol=1e-5)


def test_pcm_features_detect_separate_frequency_bands():
    sr = 16_000; t = np.arange(sr // 8) / sr
    low = (np.sin(2*np.pi*100*t)*16000).astype(np.int16).tobytes()
    high = (np.sin(2*np.pi*4000*t)*16000).astype(np.int16).tobytes()
    _, low_bands = pcm16_features(low, sr); _, high_bands = pcm16_features(high, sr)
    assert low_bands[0] > low_bands[2]
    assert high_bands[2] > high_bands[0]


def test_audio_analyzer_smooths_and_never_retains_pcm():
    analyzer = AudioAnalyzer(); analyzer.set_bands("input", (1, .5, .25))
    before = analyzer.input.copy(); analyzer.decay(.5)
    assert np.all(analyzer.input < before)
    assert not hasattr(analyzer, "pcm")


def test_existing_audio_forwarder_delivers_rms_and_fft_without_new_stream():
    from main import _report_audio_level
    class UI:
        level = None; bands = None
        def set_input_audio_level(self, value): self.level = value
        def set_input_audio_spectrum(self, *values): self.bands = values
    ui = UI(); t = np.arange(800) / 16_000
    pcm = (np.sin(2*np.pi*100*t)*12000).astype(np.int16).tobytes()
    _report_audio_level(ui, "input", pcm)
    assert ui.level > 0 and len(ui.bands) == 3 and ui.bands[0] > ui.bands[2]


def test_widget_api_single_graph_and_raster_fallback():
    from PyQt6.QtWidgets import QApplication
    from aurora_particles.widget import ParticleMorphingCanvas
    app = QApplication.instance() or QApplication([])
    widget = ParticleMorphingCanvas(config={"graphics_quality": "low"})
    widget._timer.stop()
    graph_identity = id(widget._graph)
    assert widget.renderer_status["nodes"] == 450
    assert widget.renderer_status["connections"] == 2_000
    assert widget.renderer_status["filaments_by_layer"] == (28, 70, 160)
    assert widget.set_state("LISTENING")
    assert id(widget._graph) == graph_identity
    widget.set_input_audio_level(.2); widget.set_input_audio_spectrum(.1, .2, .3)
    widget._gpu_ready = False; widget.resize(400, 320); widget._paint_fallback()
    widget.close(); assert app is not None


def test_widget_uses_output_audio_while_speaking_and_input_otherwise():
    from PyQt6.QtWidgets import QApplication
    from aurora_particles.widget import ParticleMorphingCanvas
    app = QApplication.instance() or QApplication([])
    widget = ParticleMorphingCanvas(config={"graphics_quality": "low"}); widget._timer.stop()
    widget.set_input_audio_level(.20); widget.set_output_audio_level(.35)
    widget.set_state("LISTENING"); widget._step(); listening_rms = widget._visual_rms
    widget.set_state("SPEAKING"); widget._step()
    assert widget._visual_rms > listening_rms
    widget.close(); assert app is not None


def test_visual_lifecycle_logs_state_queue_and_completion(caplog):
    from PyQt6.QtWidgets import QApplication
    from aurora_particles.widget import ParticleMorphingCanvas
    app = QApplication.instance() or QApplication([])
    widget = ParticleMorphingCanvas(config={"graphics_quality": "low"}); widget._timer.stop()
    with caplog.at_level("INFO", logger="jarvis.aurora_particles"):
        widget.set_state("LISTENING"); widget.set_state("PROCESSING")
        for _ in range(20): widget._state_controller.update(.1)
        widget._step()
    assert "NEURAL_STATE logical=LISTENING" in caplog.text
    assert "NEURAL_TRANSITION start" in caplog.text
    assert "NEURAL_TRANSITION enqueue=processing" in caplog.text
    widget.close(); assert app is not None


def test_audio_facade_keeps_thread_safe_qt_signal_boundary():
    from ui import JarvisUI
    emitted = []
    class Signal:
        def __init__(self, name): self.name = name
        def emit(self, *values): emitted.append((self.name, values, threading.get_ident()))
    class Window:
        _input_audio_sig=Signal("input_rms"); _output_audio_sig=Signal("output_rms")
        _input_fft_sig=Signal("input_fft"); _output_fft_sig=Signal("output_fft")
    facade=JarvisUI.__new__(JarvisUI); facade._win=Window(); worker_id=[]
    def worker():
        worker_id.append(threading.get_ident()); facade.set_input_audio_level(.4)
        facade.set_input_audio_spectrum(.1,.2,.3); facade.set_output_audio_level(.5)
        facade.set_output_audio_spectrum(.3,.2,.1)
    thread=threading.Thread(target=worker); thread.start(); thread.join()
    assert [item[0] for item in emitted] == ["input_rms","input_fft","output_rms","output_fft"]
    assert all(item[2] == worker_id[0] for item in emitted)
