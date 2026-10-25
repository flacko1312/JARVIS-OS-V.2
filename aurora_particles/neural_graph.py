"""Deterministic organic neural graph used by AURORA's GPU renderer."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NeuralGraph:
    nodes: np.ndarray
    node_seed: np.ndarray
    node_role: np.ndarray
    node_depth: np.ndarray
    edge_vertices: np.ndarray
    edge_seed: np.ndarray
    edge_path: np.ndarray
    edge_depth: np.ndarray
    edge_count: int


def _unit(vector: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    return vector / max(length, 1e-6)


def build_neural_graph(node_count: int, edge_count: int, seed: int = 7319) -> NeuralGraph:
    """Build one irregular branched network with curved cross-connections.

    Edges are ordered from the denser interior toward the exterior where
    possible. That stable direction lets the fragment shader reverse impulses
    for listening without rebuilding buffers.
    """
    node_count = max(64, int(node_count))
    edge_count = max(node_count - 1, int(edge_count))
    rng = np.random.default_rng(seed + node_count * 3 + edge_count)
    nodes = np.zeros((node_count, 3), dtype=np.float32)
    parents = np.zeros(node_count, dtype=np.int32)
    branch_count = max(20, min(44, node_count // 20))
    cursor = 1

    # Compact asymmetric nucleus: no spherical shell and no orbital geometry.
    nucleus_count = max(20, int(node_count * .12))
    nodes[:nucleus_count] = rng.normal(0.0, (.13, .11, .12), (nucleus_count, 3))
    parents[1:nucleus_count] = rng.integers(0, np.arange(1, nucleus_count))
    cursor = nucleus_count

    allocations = np.full(branch_count, (node_count - cursor) // branch_count, dtype=np.int32)
    allocations[:(node_count - cursor) % branch_count] += 1
    for branch_index, amount in enumerate(allocations):
        if amount <= 0:
            continue
        azimuth = (branch_index / branch_count) * np.pi * 2.0 + rng.normal(0.0, .055)
        vertical_sign = 1.0 if np.sin(azimuth) >= 0.0 else -1.0
        direction = _unit(np.asarray((
            np.cos(azimuth) * rng.uniform(.72, .94),
            np.sin(azimuth) * rng.uniform(.86, 1.08),
            np.sin(azimuth * 2.3 + .7) * rng.uniform(.26, .48),
        ), dtype=np.float32))
        parent = int(rng.integers(0, nucleus_count))
        start = nodes[parent].copy()
        length = rng.uniform(.74, 1.08)
        endpoint = start * .18 + direction * length
        tangent = _unit(np.cross(direction, _unit(rng.normal(size=3).astype(np.float32))))
        control_a = start + direction * length * .28 + tangent * rng.uniform(.08, .18)
        control_b = start + direction * length * .70 - tangent * rng.uniform(.06, .16)
        control_b[1] += vertical_sign * rng.uniform(.03, .11)
        for step in range(int(amount)):
            index = cursor
            cursor += 1
            progress = (step + 1) / max(1, int(amount))
            omt = 1.0 - progress
            point = (
                omt**3 * start
                + 3.0 * omt**2 * progress * control_a
                + 3.0 * omt * progress**2 * control_b
                + progress**3 * endpoint
            )
            jitter = rng.normal(0.0, .006, 3).astype(np.float32) * np.sin(progress*np.pi)
            nodes[index] = point + jitter
            parents[index] = parent
            parent = index

    # Normalize into an anisotropic, slightly tilted volume with open negative
    # space. This keeps the silhouette organic instead of becoming a ball.
    nodes -= nodes.mean(axis=0, keepdims=True)
    nodes[:, 0] *= 1.12
    nodes[:, 1] *= 1.06
    nodes[:, 2] *= .94
    radius = np.percentile(np.linalg.norm(nodes, axis=1), 99.5)
    nodes /= max(float(radius), 1e-6)
    nodes *= .88

    edges: list[tuple[int, int]] = [(int(parents[i]), i) for i in range(1, node_count)]
    seen = {tuple(sorted(edge)) for edge in edges}
    # Add local cross-links. Candidate sampling avoids a large NxN allocation.
    while len(edges) < edge_count:
        a = int(rng.integers(0, node_count))
        candidates = rng.integers(0, node_count, size=18)
        distances = np.linalg.norm(nodes[candidates] - nodes[a], axis=1)
        b = int(candidates[int(np.argmin(distances + (candidates == a) * 100.0))])
        key = tuple(sorted((a, b)))
        if a == b or key in seen:
            continue
        # Keep graph routes local enough to read as filaments, not chords.
        if float(np.linalg.norm(nodes[a] - nodes[b])) > .24:
            continue
        seen.add(key)
        if np.linalg.norm(nodes[a]) <= np.linalg.norm(nodes[b]):
            edges.append((a, b))
        else:
            edges.append((b, a))

    # Each curved connection is three independent GL_LINES segments sampled
    # from a quadratic Bezier. Curvature is deterministic and stored once.
    subdivisions = 3
    edge_vertices = np.empty((edge_count * subdivisions * 2, 3), dtype=np.float32)
    edge_seed_values = np.empty(edge_count * subdivisions * 2, dtype=np.float32)
    edge_path = np.empty(edge_count * subdivisions * 2, dtype=np.float32)
    edge_depth = np.empty(edge_count * subdivisions * 2, dtype=np.float32)
    write = 0
    seeds = rng.random(edge_count).astype(np.float32)
    for edge_index, (a, b) in enumerate(edges[:edge_count]):
        start, end = nodes[a], nodes[b]
        delta = end - start
        normal = np.cross(delta, np.asarray((.21, .73, .43), dtype=np.float32))
        if np.linalg.norm(normal) < 1e-5:
            normal = np.cross(delta, np.asarray((.77, .12, .61), dtype=np.float32))
        normal = _unit(normal)
        bend = normal * min(.055, float(np.linalg.norm(delta)) * .22) * (1 if seeds[edge_index] > .5 else -1)
        control = (start + end) * .5 + bend
        for segment in range(subdivisions):
            for t in (segment / subdivisions, (segment + 1) / subdivisions):
                omt = 1.0 - t
                point = omt * omt * start + 2.0 * omt * t * control + t * t * end
                edge_vertices[write] = point
                edge_seed_values[write] = seeds[edge_index]
                edge_path[write] = t
                edge_depth[write] = np.clip((point[2] + 1.0) * .5, 0.0, 1.0)
                write += 1

    radii = np.linalg.norm(nodes, axis=1)
    node_role = np.clip(radii / max(float(radii.max()), 1e-6), 0.0, 1.0).astype(np.float32)
    node_depth = np.clip((nodes[:, 2] + 1.0) * .5, 0.0, 1.0).astype(np.float32)
    node_seed = rng.random(node_count).astype(np.float32)
    return NeuralGraph(
        nodes=np.ascontiguousarray(nodes),
        node_seed=node_seed,
        node_role=node_role,
        node_depth=node_depth,
        edge_vertices=np.ascontiguousarray(edge_vertices),
        edge_seed=edge_seed_values,
        edge_path=edge_path,
        edge_depth=edge_depth,
        edge_count=edge_count,
    )
