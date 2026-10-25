"""Deterministic organic filament field used by AURORA's GPU renderer."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NeuralGraph:
    """Logical particles plus a separate spline-based visual representation."""

    nodes: np.ndarray
    node_seed: np.ndarray
    node_role: np.ndarray
    node_depth: np.ndarray
    edge_vertices: np.ndarray
    edge_seed: np.ndarray
    edge_path: np.ndarray
    edge_depth: np.ndarray
    edge_layer: np.ndarray
    edge_count: int
    filament_count: int
    filament_segment_counts: tuple[int, ...]
    layer_segment_counts: tuple[int, int, int]


def _polar(radius: float, angle: float, z: float) -> np.ndarray:
    return np.asarray((radius * np.cos(angle), radius * np.sin(angle), z), dtype=np.float32)


def _segment_budget(total: int, counts: tuple[int, int, int]) -> list[list[int]]:
    """Distribute an exact segment budget while keeping every spline smooth."""
    weights = (.38, .44, .18)
    targets = [int(total * weight) for weight in weights]
    targets[-1] += total - sum(targets)
    result: list[list[int]] = []
    for target, count in zip(targets, counts):
        base = max(6, target // count)
        layer = [base] * count
        delta = target - sum(layer)
        index = 0
        while delta > 0:
            layer[index % count] += 1
            delta -= 1
            index += 1
        while delta < 0:
            slot = index % count
            if layer[slot] > 6:
                layer[slot] -= 1
                delta += 1
            index += 1
        result.append(layer)
    return result


def _cubic(start: np.ndarray, control_a: np.ndarray, control_b: np.ndarray,
           end: np.ndarray, steps: int) -> np.ndarray:
    t = np.linspace(0.0, 1.0, steps + 1, dtype=np.float32)[:, None]
    omt = 1.0 - t
    return (
        omt**3 * start
        + 3.0 * omt**2 * t * control_a
        + 3.0 * omt * t**2 * control_b
        + t**3 * end
    ).astype(np.float32)


def build_neural_graph(node_count: int, edge_count: int, seed: int = 7319) -> NeuralGraph:
    """Build a layered field of long cubic filaments around one bright core.

    ``edge_count`` is the exact rendered line-segment budget. Logical nodes are
    sampled from the curves but are intentionally independent from the visual
    topology: the renderer never needs to expose a graph of node-to-node links.
    """
    node_count = max(64, int(node_count))
    edge_count = max(360, int(edge_count))
    rng = np.random.default_rng(seed + node_count * 3 + edge_count)

    filament_count = max(42, min(150, node_count // 8))
    main_count = max(12, int(filament_count * .25))
    secondary_count = max(20, int(filament_count * .50))
    wisp_count = filament_count - main_count - secondary_count
    layer_counts = (main_count, secondary_count, wisp_count)
    budgets = _segment_budget(edge_count, layer_counts)

    vertices: list[np.ndarray] = []
    seeds: list[float] = []
    paths: list[float] = []
    depths: list[float] = []
    layers: list[float] = []
    sampled_paths: list[np.ndarray] = []
    filament_segments: list[int] = []
    layer_segment_totals = [0, 0, 0]

    for layer, (count, segment_counts) in enumerate(zip(layer_counts, budgets)):
        for filament_index, segments in enumerate(segment_counts):
            identity = float(rng.random())
            base_angle = (
                filament_index / max(1, count) * np.pi * 2.0
                + layer * .17
                + rng.normal(0.0, .075 + layer * .025)
            )
            handedness = -1.0 if (filament_index + layer) % 2 else 1.0
            if layer == 0:
                start_radius = rng.uniform(.010, .055)
                end_radius = rng.uniform(.78, 1.02)
                curl = rng.uniform(.55, .96) * handedness
                z_scale = .38
            elif layer == 1:
                start_radius = rng.uniform(.025, .115)
                end_radius = rng.uniform(.52, .88)
                curl = rng.uniform(.40, .78) * handedness
                z_scale = .52
            else:
                start_radius = rng.uniform(.055, .20)
                end_radius = rng.uniform(.34, .70)
                curl = rng.uniform(.28, .64) * handedness
                z_scale = .70

            end_angle = base_angle + rng.normal(0.0, .14) + curl * rng.uniform(.25, .50)
            start = _polar(start_radius, base_angle + curl * .12, rng.uniform(-.055, .055))
            end = _polar(end_radius, end_angle, rng.uniform(-z_scale, z_scale))
            control_a = _polar(
                end_radius * rng.uniform(.18, .31),
                base_angle + curl * rng.uniform(.78, 1.14),
                rng.uniform(-z_scale, z_scale) * .35,
            )
            control_b = _polar(
                end_radius * rng.uniform(.54, .78),
                end_angle - curl * rng.uniform(.48, .88),
                end[2] * rng.uniform(.48, .82) + rng.uniform(-.10, .10),
            )
            points = _cubic(start, control_a, control_b, end, segments)
            progress = np.linspace(0.0, 1.0, segments + 1, dtype=np.float32)
            lift = np.sin(progress * np.pi) * rng.uniform(.028, .090) * handedness
            tangent = np.asarray((-np.sin(base_angle), np.cos(base_angle)), dtype=np.float32)
            points[:, :2] += lift[:, None] * tangent
            sampled_paths.append(points)
            filament_segments.append(segments)
            layer_segment_totals[layer] += segments
            for segment in range(segments):
                for point_index in (segment, segment + 1):
                    point = points[point_index]
                    vertices.append(point)
                    seeds.append(identity)
                    paths.append(point_index / segments)
                    depths.append(float(np.clip((point[2] + 1.0) * .5, 0.0, 1.0)))
                    layers.append(float(layer))

    edge_vertices = np.ascontiguousarray(np.asarray(vertices, dtype=np.float32))
    route_points = np.concatenate(sampled_paths, axis=0)
    nucleus_count = max(28, int(node_count * .16))
    nodes = np.empty((node_count, 3), dtype=np.float32)
    nodes[:nucleus_count] = rng.normal(0.0, (.095, .082, .090), (nucleus_count, 3))
    sample_indices = np.linspace(0, len(route_points) - 1, node_count - nucleus_count, dtype=np.int32)
    rng.shuffle(sample_indices)
    nodes[nucleus_count:] = route_points[sample_indices]
    nodes[nucleus_count:] += rng.normal(0.0, .004, (node_count - nucleus_count, 3)).astype(np.float32)

    max_radius = max(float(np.percentile(np.linalg.norm(nodes, axis=1), 99.7)), 1e-6)
    if max_radius > 1.02:
        nodes /= max_radius / 1.02
        edge_vertices /= max_radius / 1.02
    radii = np.linalg.norm(nodes[:, :2], axis=1)
    node_role = np.clip(radii / max(float(radii.max()), 1e-6), 0.0, 1.0).astype(np.float32)
    node_depth = np.clip((nodes[:, 2] + 1.0) * .5, 0.0, 1.0).astype(np.float32)

    return NeuralGraph(
        nodes=np.ascontiguousarray(nodes),
        node_seed=rng.random(node_count).astype(np.float32),
        node_role=node_role,
        node_depth=node_depth,
        edge_vertices=edge_vertices,
        edge_seed=np.asarray(seeds, dtype=np.float32),
        edge_path=np.asarray(paths, dtype=np.float32),
        edge_depth=np.asarray(depths, dtype=np.float32),
        edge_layer=np.asarray(layers, dtype=np.float32),
        edge_count=edge_count,
        filament_count=filament_count,
        filament_segment_counts=tuple(filament_segments),
        layer_segment_counts=tuple(layer_segment_totals),
    )
