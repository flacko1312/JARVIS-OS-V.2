"""Deterministic hierarchical filament field for AURORA's GPU renderer."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NeuralGraph:
    """Logical particles plus a separate branching spline representation."""

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
    layer_filament_counts: tuple[int, int, int]
    filament_segment_counts: tuple[int, ...]
    layer_segment_counts: tuple[int, int, int]


def _polar(radius: float, angle: float, z: float = 0.0) -> np.ndarray:
    return np.asarray((radius * np.cos(angle), radius * np.sin(angle), z), dtype=np.float32)


def _unit_xy(vector: np.ndarray) -> np.ndarray:
    length = max(float(np.linalg.norm(vector[:2])), 1e-6)
    return np.asarray((vector[0] / length, vector[1] / length, 0.0), dtype=np.float32)


def _layer_profile(node_count: int) -> tuple[int, int, int]:
    if node_count <= 500:
        return 28, 70, 160
    if node_count <= 900:
        return 42, 110, 280
    return 52, 150, 380


def _segment_budget(total: int, counts: tuple[int, int, int]) -> list[list[int]]:
    """Allocate more curve resolution to trunks than background microfibres."""
    minimum = (10, 5, 6)
    layers = [[minimum[index]] * count for index, count in enumerate(counts)]
    remaining = total - sum(len(layer) * minimum[index] for index, layer in enumerate(layers))
    if remaining < 0:
        raise ValueError("segment budget is too small for filament profile")
    weights = (.58, .27, .15)
    extras = [int(remaining * weight) for weight in weights]
    extras[-1] += remaining - sum(extras)
    for layer, extra in zip(layers, extras):
        for index in range(extra):
            layer[index % len(layer)] += 1
    return layers


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


def _main_route(rng: np.random.Generator, index: int, count: int,
                segments: int) -> np.ndarray:
    angle = index / count * np.pi * 2.0 + rng.normal(0.0, .11)
    handedness = -1.0 if index % 2 else 1.0
    curl = rng.uniform(.58, 1.08) * handedness
    radius = rng.uniform(.70, 1.06)
    start = _polar(rng.uniform(.008, .050), angle + curl * .08, rng.uniform(-.045, .045))
    end_angle = angle + curl * rng.uniform(.28, .55) + rng.normal(0.0, .10)
    end = _polar(radius, end_angle, rng.uniform(-.42, .42))
    control_a = _polar(radius * rng.uniform(.17, .30), angle + curl * rng.uniform(.82, 1.22), rng.uniform(-.16, .16))
    control_b = _polar(radius * rng.uniform(.50, .78), end_angle - curl * rng.uniform(.50, .92), end[2] * rng.uniform(.45, .82))
    points = _cubic(start, control_a, control_b, end, segments)
    progress = np.linspace(0.0, 1.0, segments + 1, dtype=np.float32)
    tangent = np.asarray((-np.sin(angle), np.cos(angle)), dtype=np.float32)
    points[:, :2] += (np.sin(progress * np.pi) * rng.uniform(.025, .105) * handedness)[:, None] * tangent
    return points


def _child_route(rng: np.random.Generator, parents: list[np.ndarray], layer: int,
                 segments: int) -> np.ndarray:
    parent = parents[int(rng.integers(0, len(parents)))]
    low, high = ((.24, .76) if layer == 1 else (.12, .94))
    parent_index = int(rng.uniform(low, high) * (len(parent) - 1))
    start = parent[parent_index].copy()
    before = parent[max(0, parent_index - 1)]
    after = parent[min(len(parent) - 1, parent_index + 1)]
    direction = _unit_xy(after - before)
    parent_angle = float(np.arctan2(direction[1], direction[0]))
    handedness = -1.0 if rng.random() < .5 else 1.0
    if layer == 1:
        length = rng.uniform(.24, .62)
        curl = rng.uniform(.44, .96) * handedness
        departure = rng.uniform(.18, .72) * handedness
        z_delta = rng.uniform(-.42, .42)
    else:
        length = rng.uniform(.075, .31)
        curl = rng.uniform(.35, 1.16) * handedness
        departure = rng.uniform(.24, 1.02) * handedness
        z_delta = rng.uniform(-.56, .56)
    angle = parent_angle + departure
    end_angle = angle + curl * rng.uniform(.28, .62)
    end = start + _polar(length, end_angle, z_delta)
    radius = float(np.linalg.norm(end[:2]))
    if radius > 1.08:
        end[:2] *= 1.08 / radius
    control_a = start + _polar(length * rng.uniform(.20, .34), angle + curl * rng.uniform(.60, 1.05), z_delta * .18)
    control_b = start + _polar(length * rng.uniform(.58, .82), end_angle - curl * rng.uniform(.38, .80), z_delta * .68)
    return _cubic(start, control_a, control_b, end, segments)


def build_neural_graph(node_count: int, edge_count: int, seed: int = 7319) -> NeuralGraph:
    """Build trunks, child branches and microfibres without node-to-node links."""
    node_count = max(64, int(node_count))
    edge_count = max(900, int(edge_count))
    rng = np.random.default_rng(seed + node_count * 3 + edge_count)
    layer_counts = _layer_profile(node_count)
    budgets = _segment_budget(edge_count, layer_counts)

    vertices: list[np.ndarray] = []
    seeds: list[float] = []
    paths: list[float] = []
    depths: list[float] = []
    layers: list[float] = []
    sampled_by_layer: list[list[np.ndarray]] = [[], [], []]
    sampled_paths: list[np.ndarray] = []
    filament_segments: list[int] = []
    layer_segment_totals = [0, 0, 0]

    for layer, (count, segment_counts) in enumerate(zip(layer_counts, budgets)):
        for filament_index, segments in enumerate(segment_counts):
            if layer == 0:
                points = _main_route(rng, filament_index, count, segments)
            else:
                parent_pool = sampled_by_layer[layer - 1]
                if layer == 2 and rng.random() < .24:
                    parent_pool = sampled_by_layer[0]
                points = _child_route(rng, parent_pool, layer, segments)
            identity = float(rng.random())
            sampled_by_layer[layer].append(points)
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
    nucleus_count = max(34, int(node_count * .18))
    nodes = np.empty((node_count, 3), dtype=np.float32)
    nodes[:nucleus_count] = rng.normal(0.0, (.10, .087, .095), (nucleus_count, 3))
    sample_indices = np.linspace(0, len(route_points) - 1, node_count - nucleus_count, dtype=np.int32)
    rng.shuffle(sample_indices)
    nodes[nucleus_count:] = route_points[sample_indices]
    nodes[nucleus_count:] += rng.normal(0.0, .004, (node_count - nucleus_count, 3)).astype(np.float32)

    max_radius = max(float(np.percentile(np.linalg.norm(nodes, axis=1), 99.7)), 1e-6)
    if max_radius > 1.06:
        scale = 1.06 / max_radius
        nodes *= scale
        edge_vertices *= scale
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
        filament_count=sum(layer_counts),
        layer_filament_counts=layer_counts,
        filament_segment_counts=tuple(filament_segments),
        layer_segment_counts=tuple(layer_segment_totals),
    )
