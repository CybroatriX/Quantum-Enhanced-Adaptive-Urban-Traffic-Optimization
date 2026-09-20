"""Perception package for computer vision, vehicle detection, and observation models."""

from perception.aggregator import TrafficAggregator, point_in_polygon
from perception.detector import YOLOVehicleDetector
from perception.models import TrafficObservation, VALID_APPROACHES, VALID_VEHICLE_CLASSES, VehicleDetection
from perception.queue_estimator import MotionState, QueueEstimator
from perception.service import (
    HARDWARE_DISCLAIMER,
    PERCEPTION_DISCLAIMER,
    PerceptionConfig,
    RealWorldPerceptionService,
    SourceType,
    sanitize_rtsp_url,
)

__all__ = [
    "HARDWARE_DISCLAIMER",
    "MotionState",
    "PERCEPTION_DISCLAIMER",
    "PerceptionConfig",
    "QueueEstimator",
    "RealWorldPerceptionService",
    "SourceType",
    "TrafficAggregator",
    "TrafficObservation",
    "VALID_APPROACHES",
    "VALID_VEHICLE_CLASSES",
    "VehicleDetection",
    "YOLOVehicleDetector",
    "point_in_polygon",
    "sanitize_rtsp_url",
]

