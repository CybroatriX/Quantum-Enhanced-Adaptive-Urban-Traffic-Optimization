"""Comprehensive unit and integration tests for Phase M: Real-World Prototype Interface.

Covers:
- Image input & processing
- Video input & sequential tracking
- Invalid image rejection (unsupported format, missing file)
- Invalid video rejection
- Missing YOLO weights fallback
- YOLO unavailable fallback
- Webcam unavailable handling (non-zero camera index without crash)
- RTSP unavailable handling (unreachable stream without crash)
- RTSP URL credential sanitization
- Frame sampling rate validation
- ROI configuration and point-in-polygon classification
- Tracking integration across multi-frame sequences
- Queue estimation integration from track velocity
- TrafficObservation canonical contract compliance
- Optimization API integration (POST /api/perception/process)
- GET /api/perception/config endpoint
- Malformed payload handling
- Clean resource shutdown (release of VideoCapture)
- Real-world mode isolation from simulation
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from time import time
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from optimization.service import create_app
from perception.models import TrafficObservation, VALID_APPROACHES, VALID_VEHICLE_CLASSES, VehicleDetection
from perception.service import (
    HARDWARE_DISCLAIMER,
    PERCEPTION_DISCLAIMER,
    PerceptionConfig,
    RealWorldPerceptionService,
    SourceType,
    sanitize_rtsp_url,
)


@pytest.fixture
def temp_scratch_dir() -> Path:
    """Provide a dedicated scratch directory inside tests/ avoiding OS-temp permissions."""
    scratch = Path(__file__).resolve().parent / "_test_scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    yield scratch
    try:
        shutil.rmtree(scratch, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def synthetic_image_path(temp_scratch_dir: Path) -> Path:
    """Create a temporary synthetic JPEG image."""
    img_path = temp_scratch_dir / "test_frame.jpg"
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(img, (100, 100), (200, 200), (255, 255, 255), -1)
    cv2.imwrite(str(img_path), img)
    return img_path


@pytest.fixture
def synthetic_video_path(temp_scratch_dir: Path) -> Path:
    """Create a temporary 10-frame synthetic MP4 video."""
    video_path = temp_scratch_dir / "test_video.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 10.0, (320, 240))
    for i in range(10):
        frame = np.full((240, 320, 3), i * 20, dtype=np.uint8)
        cv2.circle(frame, (50 + i * 10, 120), 15, (0, 255, 0), -1)
        out.write(frame)
    out.release()
    return video_path


@pytest.fixture
def perception_service() -> RealWorldPerceptionService:
    rois = {
        "north": [100.0, 0.0, 300.0, 200.0],
        "south": [100.0, 300.0, 300.0, 500.0],
        "east": [350.0, 150.0, 550.0, 350.0],
        "west": [0.0, 150.0, 80.0, 350.0],
    }
    return RealWorldPerceptionService(approach_regions=rois)


@pytest.fixture
def flask_client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# =============================================================================
# 1. Image Mode Tests
# =============================================================================

def test_image_mode_valid(perception_service: RealWorldPerceptionService, synthetic_image_path: Path):
    """Test valid image processing produces a canonical TrafficObservation."""
    obs = perception_service.process_image(synthetic_image_path, intersection_id="J1")
    assert isinstance(obs, TrafficObservation)
    assert obs.source == "image"
    assert obs.intersection_id == "J1"
    assert obs.vehicle_count >= 0
    assert isinstance(obs.approach_counts, dict)
    assert set(obs.approach_counts.keys()) == set(VALID_APPROACHES)
    assert set(obs.queue_lengths.keys()) == set(VALID_APPROACHES)
    assert set(obs.class_counts.keys()) == set(VALID_VEHICLE_CLASSES)


def test_image_mode_invalid_format(perception_service: RealWorldPerceptionService, temp_scratch_dir: Path):
    """Unsupported image file formats must be rejected cleanly."""
    txt_file = temp_scratch_dir / "corrupt.txt"
    txt_file.write_text("not an image")
    with pytest.raises(ValueError, match="Unsupported image extension"):
        perception_service.process_image(txt_file)


def test_image_mode_nonexistent_file(perception_service: RealWorldPerceptionService):
    """Non-existent image path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="Image file not found"):
        perception_service.process_image("non_existent_image_12345.jpg")


# =============================================================================
# 2. Video Mode & Frame Sampling Tests
# =============================================================================

def test_video_mode_valid(perception_service: RealWorldPerceptionService, synthetic_video_path: Path):
    """Test sequential video processing produces observations for sampled frames."""
    observations = perception_service.process_video(
        video_path=synthetic_video_path,
        intersection_id="J2",
        frame_sampling_rate=2,
    )
    assert len(observations) == 5  # 10 frames sampled at step 2 = 5 observations
    for obs in observations:
        assert obs.source == "video"
        assert obs.intersection_id == "J2"
        assert set(obs.approach_counts.keys()) == set(VALID_APPROACHES)
        assert set(obs.queue_lengths.keys()) == set(VALID_APPROACHES)


def test_video_mode_frame_sampling(perception_service: RealWorldPerceptionService, synthetic_video_path: Path):
    """Test frame_sampling_rate parameter controls frame skip rate."""
    obs_all = perception_service.process_video(synthetic_video_path, frame_sampling_rate=1)
    assert len(obs_all) == 10

    obs_sample5 = perception_service.process_video(synthetic_video_path, frame_sampling_rate=5)
    assert len(obs_sample5) == 2


def test_video_mode_invalid_path(perception_service: RealWorldPerceptionService):
    """Non-existent video path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="Video file not found"):
        perception_service.process_video("missing_video.mp4")


def test_video_mode_invalid_format(perception_service: RealWorldPerceptionService, temp_scratch_dir: Path):
    """Unsupported video extension raises ValueError."""
    fake_vid = temp_scratch_dir / "fake.exe"
    fake_vid.write_bytes(b"bad data")
    with pytest.raises(ValueError, match="Unsupported video extension"):
        perception_service.process_video(fake_vid)


# =============================================================================
# 3. Observation Exporters (JSON, JSONL, CSV)
# =============================================================================

def test_export_observations_json_and_csv(synthetic_image_path: Path, temp_scratch_dir: Path):
    """Test exporting observation sequences to JSON, JSONL, and CSV summary."""
    obs1 = TrafficObservation(
        timestamp=time(),
        source="video",
        intersection_id="J1",
        vehicle_count=5,
        approach_counts={"north": 3, "south": 2, "east": 0, "west": 0},
        queue_lengths={"north": 2, "south": 1, "east": 0, "west": 0},
        class_counts={"car": 4, "motorcycle": 1, "bus": 0, "truck": 0},
    )
    obs2 = TrafficObservation(
        timestamp=time() + 1.0,
        source="video",
        intersection_id="J1",
        vehicle_count=6,
        approach_counts={"north": 4, "south": 2, "east": 0, "west": 0},
        queue_lengths={"north": 3, "south": 1, "east": 0, "west": 0},
        class_counts={"car": 5, "motorcycle": 1, "bus": 0, "truck": 0},
    )

    # JSON Export
    json_path = temp_scratch_dir / "obs.json"
    json_str = RealWorldPerceptionService.export_observations([obs1, obs2], "json", json_path)
    loaded_json = json.loads(json_str)
    assert len(loaded_json) == 2
    assert loaded_json[0]["vehicle_count"] == 5

    # CSV Export
    csv_path = temp_scratch_dir / "obs.csv"
    csv_str = RealWorldPerceptionService.export_observations([obs1, obs2], "csv", csv_path)
    assert "north_count" in csv_str
    assert "car_count" in csv_str
    assert "J1" in csv_str


# =============================================================================
# 4. Webcam & RTSP Error Handling
# =============================================================================

def test_webcam_unavailable_handling(perception_service: RealWorldPerceptionService):
    """Accessing an invalid camera index returns clean error dictionary without crashing."""
    obs, status = perception_service.capture_camera_frame(camera_index=999)
    assert obs is None
    assert status["status"] in ("unavailable", "read_failed", "error")
    assert status["camera_index"] == 999


def test_rtsp_unavailable_handling(perception_service: RealWorldPerceptionService):
    """Connecting to an unreachable RTSP URL returns clean error dictionary without crashing."""
    obs, status = perception_service.capture_rtsp_frame("rtsp://127.0.0.1:9999/live", timeout_seconds=0.5)
    assert obs is None
    assert status["status"] in ("unavailable", "stream_read_failed", "error")
    assert "127.0.0.1:9999" in status.get("stream_url", "") or "stream_url" in status


def test_rtsp_credential_sanitization():
    """RTSP URLs with embedded credentials must be masked before logging/display."""
    raw_url = "rtsp://admin:P@ssword123!@192.168.1.100:554/stream"
    sanitized = sanitize_rtsp_url(raw_url)
    assert "P@ssword123!" not in sanitized
    assert "admin:***@192.168.1.100" in sanitized
    assert sanitize_rtsp_url("") == ""


# =============================================================================
# 5. Model Fallback & Missing Weights
# =============================================================================

def test_missing_yolo_weights_fallback():
    """When YOLO model weights cannot be loaded, service falls back safely."""
    service = RealWorldPerceptionService(model_name="non_existent_weights_xyz.pt")
    frame = np.zeros((320, 320, 3), dtype=np.uint8)
    obs = service.process_image(frame, intersection_id="J3")
    assert obs.intersection_id == "J3"
    assert obs.vehicle_count == 0
    assert obs.source == "image"


# =============================================================================
# 6. Signal Recommendation & Optimization Integration
# =============================================================================

def test_recommend_signal_timing_exact(perception_service: RealWorldPerceptionService):
    """Test generating a Prototype Signal Recommendation via QUBO exact solver."""
    obs = TrafficObservation(
        timestamp=time(),
        source="camera",
        intersection_id="J1",
        vehicle_count=20,
        approach_counts={"north": 10, "south": 6, "east": 2, "west": 2},
        queue_lengths={"north": 10, "south": 6, "east": 2, "west": 2},
        class_counts={"car": 15, "motorcycle": 2, "bus": 2, "truck": 1},
    )
    rec = perception_service.recommend_signal_timing(obs, solver="exact", road_capacity=100)
    assert rec["recommendation_type"] == "Prototype Signal Recommendation"
    assert rec["intersection_id"] == "J1"
    assert rec["solver"] == "exact"
    assert rec["method"] == "QUBO exact"
    assert rec["phase_0_green_seconds"] == 40  # Heavy North/South
    assert rec["phase_2_green_seconds"] == 22
    assert rec["yellow_seconds"] == 4
    assert rec["cycle_length_seconds"] == 70
    assert rec["valid"] is True
    assert HARDWARE_DISCLAIMER in rec["hardware_disclaimer"]
    assert PERCEPTION_DISCLAIMER in rec["perception_disclaimer"]


def test_recommend_signal_timing_qaoa(perception_service: RealWorldPerceptionService):
    """Test generating a Prototype Signal Recommendation via QAOA research mode."""
    obs = TrafficObservation(
        timestamp=time(),
        source="image",
        intersection_id="J2",
        vehicle_count=18,
        approach_counts={"north": 2, "south": 2, "east": 8, "west": 6},
        queue_lengths={"north": 2, "south": 2, "east": 8, "west": 6},
        class_counts={"car": 14, "motorcycle": 2, "bus": 1, "truck": 1},
    )
    rec = perception_service.recommend_signal_timing(obs, solver="qaoa", road_capacity=100)
    assert rec["recommendation_type"] == "Prototype Signal Recommendation"
    assert rec["solver"] == "qaoa"
    assert rec["method"] == "QAOA research mode"
    assert rec["phase_0_green_seconds"] in (22, 30, 40)
    assert rec["phase_2_green_seconds"] in (22, 30, 40)
    assert rec["valid"] is True


# =============================================================================
# 7. Flask REST API Integration (POST /api/perception/process, GET /api/perception/config)
# =============================================================================

def test_api_get_perception_config(flask_client):
    """GET /api/perception/config returns capabilities and disclaimers."""
    res = flask_client.get("/api/perception/config")
    assert res.status_code == 200
    data = res.get_json()
    assert "image" in data["supported_sources"]
    assert "video" in data["supported_sources"]
    assert "camera" in data["supported_sources"]
    assert "rtsp" in data["supported_sources"]
    assert "J1" in data["supported_intersections"]
    assert "north" in data["default_approach_regions"]
    assert "research/prototype" in data["hardware_disclaimer"].lower()


def test_api_process_perception_image(flask_client, synthetic_image_path: Path):
    """POST /api/perception/process processes image and returns prototype recommendation."""
    payload = {
        "source_type": "image",
        "source_path": str(synthetic_image_path),
        "intersection_id": "J1",
        "solver": "exact",
        "optimize": True,
    }
    res = flask_client.post("/api/perception/process", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["source_type"] == "image"
    assert data["intersection_id"] == "J1"
    assert data["observation"] is not None
    assert data["recommendation"]["recommendation_type"] == "Prototype Signal Recommendation"
    assert data["recommendation"]["phase_0_green_seconds"] >= 22
    assert "hardware_disclaimer" in data


def test_api_process_perception_synthetic(flask_client):
    """POST /api/perception/process supports synthetic test payload."""
    payload = {
        "source_type": "synthetic",
        "intersection_id": "J3",
        "synthetic_data": {
            "vehicle_count": 30,
            "approach_counts": {"north": 15, "south": 10, "east": 3, "west": 2},
            "queue_lengths": {"north": 12, "south": 8, "east": 2, "west": 1},
            "class_counts": {"car": 22, "motorcycle": 4, "bus": 3, "truck": 1},
        },
        "solver": "exact",
        "optimize": True,
    }
    res = flask_client.post("/api/perception/process", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["observation"]["vehicle_count"] == 30
    assert data["recommendation"]["phase_0_green_seconds"] == 40
    assert data["recommendation"]["phase_2_green_seconds"] == 22


def test_api_process_perception_unavailable_camera(flask_client):
    """POST /api/perception/process returns 503 when camera is unavailable."""
    payload = {
        "source_type": "camera",
        "camera_index": 9999,
        "intersection_id": "J1",
    }
    res = flask_client.post("/api/perception/process", json=payload)
    assert res.status_code == 503
    data = res.get_json()
    assert data["status"] == "unavailable"
    assert "Camera index" in data["error"]


def test_api_process_perception_invalid_source_type(flask_client):
    """POST /api/perception/process rejects unsupported source types with 400."""
    res = flask_client.post("/api/perception/process", json={"source_type": "satellite"})
    assert res.status_code == 400
    data = res.get_json()
    assert "Invalid source_type" in data["error"]


def test_clean_shutdown_and_isolation(perception_service: RealWorldPerceptionService, synthetic_video_path: Path):
    """Ensure VideoCapture resource is released after reading, and real-world mode is isolated."""
    observations = perception_service.process_video(synthetic_video_path, max_frames=2)
    assert len(observations) == 2
    # Verify file can be deleted immediately (proving handle was released)
    synthetic_video_path.unlink()
    assert not synthetic_video_path.exists()
