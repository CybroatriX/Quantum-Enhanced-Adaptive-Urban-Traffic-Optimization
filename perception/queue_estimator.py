"""Prototype queue estimation for urban traffic approaches.

NOTE: This is a prototype-level queue estimator designed for algorithmic research
and simulation coupling. It estimates queue length from 2D pixel displacements and
track histories. It is not a calibrated production traffic-engineering measurement system.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from time import time
from typing import Any, Mapping, Sequence

from perception.models import VehicleDetection


class MotionState(str, Enum):
    """Estimated vehicle motion state based on frame-to-frame displacement."""

    STOPPED = "stopped"
    SLOW = "slow"
    MOVING = "moving"
    UNKNOWN = "unknown"


@dataclass
class TrackHistoryPoint:
    """Historical center position of a tracked vehicle at a given timestamp."""

    x: float
    y: float
    timestamp: float


class QueueEstimator:
    """Estimates approach queue lengths from tracked vehicle velocity and positions.

    Identifies vehicles that are stationary or moving below configured speed thresholds
    within each intersection approach region (north, south, east, west).
    """

    def __init__(
        self,
        stopped_speed_threshold: float = 5.0,  # pixels or units per second
        slow_speed_threshold: float = 15.0,  # pixels or units per second
        include_slow_in_queue: bool = True,
        min_history_points: int = 2,
        history_window_seconds: float = 5.0,
        first_frame_default_state: MotionState = MotionState.STOPPED,
        untracked_default_state: MotionState = MotionState.STOPPED,
    ) -> None:
        self.stopped_speed_threshold = float(stopped_speed_threshold)
        self.slow_speed_threshold = float(slow_speed_threshold)
        self.include_slow_in_queue = bool(include_slow_in_queue)
        self.min_history_points = int(min_history_points)
        self.history_window_seconds = float(history_window_seconds)
        self.first_frame_default_state = first_frame_default_state
        self.untracked_default_state = untracked_default_state

        if self.stopped_speed_threshold < 0.0:
            raise ValueError("stopped_speed_threshold must be non-negative.")
        if self.slow_speed_threshold < self.stopped_speed_threshold:
            raise ValueError("slow_speed_threshold must be >= stopped_speed_threshold.")

        # track_id -> list of TrackHistoryPoint
        self._tracks: dict[int, list[TrackHistoryPoint]] = {}

    def update_tracks(
        self, detections: Sequence[VehicleDetection], timestamp: float
    ) -> dict[int, float]:
        """Update tracking history and return computed speed for each tracked vehicle.

        Returns:
            dict mapping track_id to estimated speed (pixels/sec).
        """
        now = float(timestamp)
        speeds: dict[int, float] = {}

        # 1. Prune old history points across all tracks
        cutoff = now - self.history_window_seconds
        active_track_ids = set()

        for det in detections:
            if det.track_id is None:
                continue

            tid = det.track_id
            active_track_ids.add(tid)
            cx, cy = det.center

            if tid not in self._tracks:
                self._tracks[tid] = []

            # Append current observation point
            self._tracks[tid].append(TrackHistoryPoint(x=cx, y=cy, timestamp=now))

            # Keep only points within window
            self._tracks[tid] = [pt for pt in self._tracks[tid] if pt.timestamp >= cutoff]

            # Compute speed if enough history
            if len(self._tracks[tid]) >= self.min_history_points:
                first_pt = self._tracks[tid][0]
                last_pt = self._tracks[tid][-1]
                dt = last_pt.timestamp - first_pt.timestamp
                if dt > 1e-4:
                    dx = last_pt.x - first_pt.x
                    dy = last_pt.y - first_pt.y
                    distance = math.hypot(dx, dy)
                    speeds[tid] = distance / dt
                else:
                    speeds[tid] = 0.0

        # Remove stale tracks that disappeared past the window
        stale_ids = [tid for tid, pts in self._tracks.items() if not pts or pts[-1].timestamp < cutoff]
        for tid in stale_ids:
            del self._tracks[tid]

        return speeds

    def classify_motion(self, track_id: int | None, speeds: Mapping[int, float]) -> MotionState:
        """Classify vehicle motion state as STOPPED, SLOW, MOVING, or UNKNOWN."""
        if track_id is None:
            return self.untracked_default_state
        if track_id not in speeds:
            return self.first_frame_default_state

        speed = speeds[track_id]
        if speed <= self.stopped_speed_threshold:
            return MotionState.STOPPED
        elif speed <= self.slow_speed_threshold:
            return MotionState.SLOW
        else:
            return MotionState.MOVING

    def estimate_queues(
        self,
        detections: Sequence[VehicleDetection],
        approach_assignments: Sequence[str],
        timestamp: float | None = None,
    ) -> dict[str, int]:
        """Estimate queue counts per approach.

        Args:
            detections: List of vehicle detections in current frame.
            approach_assignments: Approach name corresponding to each detection.
            timestamp: Timestamp in seconds (defaults to current time).

        Returns:
            dict mapping approach name ('north', 'south', 'east', 'west') to queued vehicle count.
        """
        now = time() if timestamp is None else float(timestamp)
        speeds = self.update_tracks(detections, now)

        queue_counts: dict[str, int] = {"north": 0, "south": 0, "east": 0, "west": 0}

        for det, approach in zip(detections, approach_assignments):
            motion = self.classify_motion(det.track_id, speeds)

            # Determine if vehicle belongs to the queue
            is_queued = False
            if motion == MotionState.STOPPED:
                is_queued = True
            elif motion == MotionState.SLOW and self.include_slow_in_queue:
                is_queued = True

            if is_queued:
                queue_counts[approach] = queue_counts.get(approach, 0) + 1

        return queue_counts

    def reset(self) -> None:
        """Clear all tracking velocity history."""
        self._tracks.clear()
