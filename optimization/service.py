"""HTTP service exposing the canonical Phase 3A QUBO and Phase 3B QAOA optimizers.

Provides POST /api/optimize and GET /api/health endpoints for consumption by
the Node.js simulation bridge and external test runners.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from time import time
from typing import Any, Mapping

<<<<<<< HEAD
from flask import Flask, jsonify, request
=======
from flask import Flask, jsonify, request, Response
>>>>>>> a608c39 (Update Quantum Traffic Optimization project)

logger = logging.getLogger(__name__)

from config.loader import load_config
from optimization.quantum.qaoa import run_qaoa
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from metrics.evaluator import TrafficMetricsEvaluator
from perception.models import TrafficObservation
<<<<<<< HEAD
=======
from perception.realtime import RealtimeDetectionEngine
>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
from perception.service import (
    HARDWARE_DISCLAIMER,
    PERCEPTION_DISCLAIMER,
    RealWorldPerceptionService,
    sanitize_rtsp_url,
)
from simulation.models.emergency import CorridorState, EmergencyRequest
from simulation.models.events import DynamicEvent, EventStatus, EventType
from simulation.models.state import IntersectionTrafficState, SignalState
from simulation.signals.emergency import EmergencyGreenCorridorController
from simulation.signals.events import DynamicEventManager


def parse_state_data(data: dict[str, Any]) -> tuple[IntersectionTrafficState, str]:
    """Validate and convert JSON request dictionary into IntersectionTrafficState and solver name.

    Supports both snake_case API convention and camelCase simulation keys.
    """
    if not isinstance(data, dict):
        raise ValueError("State data must be a JSON object.")

    # 1. Intersection ID
    raw_id = data.get("intersection_id") if "intersection_id" in data else data.get("intersectionId")
    if raw_id is None or (isinstance(raw_id, str) and not str(raw_id).strip()):
        raise ValueError("Field 'intersection_id' is required and cannot be empty.")
    intersection_id = str(raw_id)

    # 2. Phase Queues extraction
    p0_val = data.get("phase_0_queue") if "phase_0_queue" in data else data.get("nsQueue")
    p2_val = data.get("phase_2_queue") if "phase_2_queue" in data else data.get("ewQueue")

    # Canonical TrafficObservation support: extract from approach queue_lengths
    if (p0_val is None or p2_val is None) and "queue_lengths" in data:
        raw_ql = data["queue_lengths"]
        if isinstance(raw_ql, dict):
            for k, v in raw_ql.items():
                if isinstance(v, (int, float)) and v < 0:
                    raise ValueError("Queue lengths cannot be negative.")
            if p0_val is None:
                p0_val = int(raw_ql.get("north", 0)) + int(raw_ql.get("south", 0))
            if p2_val is None:
                p2_val = int(raw_ql.get("east", 0)) + int(raw_ql.get("west", 0))

    # IntersectionTrafficState dictionary support: extract from green_phase_queues
    if (p0_val is None or p2_val is None) and "green_phase_queues" in data:
        try:
            gpq = dict(data["green_phase_queues"])
            if p0_val is None:
                p0_val = gpq.get(0, 0)
            if p2_val is None:
                p2_val = gpq.get(2, 0)
        except Exception:
            pass

    if p0_val is None:
        raise ValueError("Field 'phase_0_queue' (or 'nsQueue' / 'queue_lengths') is required.")
    if p2_val is None:
        raise ValueError("Field 'phase_2_queue' (or 'ewQueue' / 'queue_lengths') is required.")

    try:
        p0_queue = int(p0_val)
        p2_queue = int(p2_val)
    except (ValueError, TypeError) as exc:
        raise ValueError("Queue lengths must be integers.") from exc

    if p0_queue < 0 or p2_queue < 0:
        raise ValueError("Queue lengths cannot be negative.")

    # 3. Vehicle Count & Road Capacity
    raw_vehicles = data.get("vehicle_count") if "vehicle_count" in data else data.get("vehicleCount")
    vehicle_count = p0_queue + p2_queue if raw_vehicles is None else int(raw_vehicles)
    if vehicle_count < 0:
        raise ValueError("Vehicle count cannot be negative.")

    raw_capacity = data.get("road_capacity") if "road_capacity" in data else data.get("roadCapacity", 100)
    road_capacity = int(raw_capacity)
    if road_capacity <= 0:
        raise ValueError("Road capacity must be greater than zero.")

    # 4. Traffic Density
    raw_density = data.get("traffic_density") if "traffic_density" in data else data.get("trafficDensity")
    if raw_density is None:
        traffic_density = min(1.0, round(vehicle_count / road_capacity, 4))
    else:
        traffic_density = float(raw_density)
    if traffic_density < 0.0:
        raise ValueError("Traffic density cannot be negative.")

    # 5. Signal Phase & State
    current_phase = int(data.get("current_signal_phase", data.get("signal_phase", 0)))
    total_queue = int(data.get("queue_length", p0_queue + p2_queue))
    emergency = bool(data.get("emergency_status", False))

    state = IntersectionTrafficState(
        intersection_id=intersection_id,
        vehicle_count=vehicle_count,
        queue_length=total_queue,
        traffic_density=traffic_density,
        road_capacity=road_capacity,
        signal_state=SignalState.GREEN,
        signal_phase=current_phase,
        emergency_status=emergency,
        green_phase_queues=((0, p0_queue), (2, p2_queue)),
    )

    # 6. Solver
    solver = str(data.get("solver", "exact")).lower()
    if solver not in ("exact", "qaoa"):
        raise ValueError(f"Unsupported solver '{solver}'. Supported solvers are 'exact' and 'qaoa'.")

    return state, solver


def optimize_intersection(
    state: IntersectionTrafficState, solver: str, config: Mapping[str, Any]
) -> dict[str, Any]:
    """Run mathematical optimization using canonical QUBO/QAOA modules."""
    model = build_qubo(state, config["optimization"]["phase3a"])

    if solver == "exact":
        solution = solve_exact(model)
        candidate = solution.candidate
        obj = solution.objective_value
        valid = candidate.valid
    else:  # qaoa
        result = run_qaoa(model, config["optimization"]["phase3b"])
        if result.best_valid_solution is None:
            raise RuntimeError("QAOA did not produce a valid signal-timing candidate.")
        candidate = result.best_valid_solution.candidate
        obj = result.best_valid_solution.objective_value
        valid = candidate.valid

    return {
        "intersection_id": state.intersection_id,
        "solver": solver,
        "phase_0_green_seconds": candidate.first_green_seconds,
        "phase_2_green_seconds": candidate.second_green_seconds,
        "objective": round(obj, 6),
        "valid": bool(valid),
    }


def create_app(custom_config: Mapping[str, Any] | None = None) -> Flask:
    """Create and configure the Flask optimizer service."""
    app = Flask(__name__)
    sim_config = custom_config or load_config()

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({
            "ok": True,
            "service": "FlowQ Canonical Python Optimizer",
            "solvers": ["exact", "qaoa"],
            "status": "ready"
        }), 200

    @app.route("/api/optimize", methods=["POST"])
    def optimize():
        if not request.is_json:
            return jsonify({"error": "Request content-type must be application/json"}), 400

        try:
            body = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Malformed or invalid JSON body"}), 400

        if not isinstance(body, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400

        # Handle batch of states or observations (multi-intersection optimization)
        batch_list = body.get("states") or body.get("observations") or body.get("intersections")
        if batch_list is not None:
            if not isinstance(batch_list, list) or not batch_list:
                return jsonify({"error": "Batch payload must contain a non-empty array of states"}), 400

            batch_solver = str(body.get("solver", "exact")).lower()
            decisions = []

            for idx, raw_state in enumerate(batch_list):
                if not isinstance(raw_state, dict):
                    return jsonify({"error": f"Item at index {idx} in batch must be an object"}), 400

                # Allow state-level solver override, fallback to batch solver
                item_data = dict(raw_state)
                if "solver" not in item_data:
                    item_data["solver"] = batch_solver

                try:
                    state, item_solver = parse_state_data(item_data)
                    result = optimize_intersection(state, item_solver, sim_config)
                except ValueError as err:
                    return jsonify({"error": f"Validation error at index {idx}: {err}"}), 400
                except RuntimeError as err:
                    return jsonify({"error": f"Optimization error at index {idx}: {err}"}), 422

                # Include compatibility keys for browser simulation
                result["intersectionId"] = raw_state.get("intersectionId", result["intersection_id"])
                result["nsGreen"] = result["phase_0_green_seconds"]
                result["ewGreen"] = result["phase_2_green_seconds"]
                result["method"] = f"QUBO {item_solver}"
                decisions.append(result)

            return jsonify({
                "method": f"QUBO {batch_solver}",
                "solver": batch_solver,
                "results": decisions,
                "decisions": decisions,
                "generatedAt": datetime.now(timezone.utc).isoformat()
            }), 200

        # Handle single intersection state
        try:
            state, solver = parse_state_data(body)
            result = optimize_intersection(state, solver, sim_config)
        except ValueError as err:
            return jsonify({"error": str(err)}), 400
        except RuntimeError as err:
            return jsonify({"error": str(err)}), 422
        except Exception as exc:
            return jsonify({"error": f"Internal optimizer error: {exc}"}), 500

        return jsonify(result), 200

    # =========================================================================
    # Emergency Green Corridor Priority Endpoints
    # =========================================================================
    emergency_controller = EmergencyGreenCorridorController()

    @app.route("/api/emergency/corridor", methods=["POST"])
    def emergency_corridor():
        if not request.is_json:
            return jsonify({"error": "Request content-type must be application/json"}), 400
        try:
            body = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Malformed JSON payload"}), 400

        if not isinstance(body, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400

        try:
            plan = emergency_controller.request_corridor(body)
        except ValueError as err:
            return jsonify({"error": str(err)}), 400
        except Exception as exc:
            return jsonify({"error": f"Corridor activation error: {exc}"}), 500

        first_plan = next(iter(plan.intersection_plans.values())) if plan.intersection_plans else None
        response_data = {
            "emergency_vehicle_id": plan.emergency_vehicle_id,
            "corridor_status": plan.corridor_status.value,
            "status": plan.corridor_status.value,
            "current_state": plan.corridor_status.value,
            "affected_intersections": plan.affected_intersections,
            "requested_approach": first_plan.priority_approach if first_plan else None,
            "requested_phase": first_plan.priority_phase if first_plan else None,
            "temporary_timing_decisions": {k: v.to_dict() for k, v in plan.intersection_plans.items()},
            "intersection_plans": {k: v.to_dict() for k, v in plan.intersection_plans.items()},
            "validation_result": plan.validation_result,
            "valid": plan.is_valid,
            "metrics": plan.metrics.to_dict() if plan.metrics else None,
        }

        status_code = 200 if plan.is_valid else 422
        return jsonify(response_data), status_code

    @app.route("/api/emergency/corridor", methods=["GET"])
    def get_emergency_corridors():
        veh_id = request.args.get("vehicle_id")
        if veh_id:
            plan = emergency_controller.get_corridor_plan(veh_id)
            if not plan:
                return jsonify({"error": f"No corridor found for vehicle '{veh_id}'"}), 404
            return jsonify(plan.to_dict()), 200
        active = emergency_controller.get_active_corridors()
        return jsonify({
            "active_corridors": {k: v.to_dict() for k, v in active.items()},
            "count": len(active),
        }), 200

    @app.route("/api/emergency/advance", methods=["POST"])
    def advance_emergency_corridor():
        if not request.is_json:
            return jsonify({"error": "Request content-type must be application/json"}), 400
        body = request.get_json(force=True)
        veh_id = body.get("emergency_vehicle_id") or body.get("vehicleId")
        curr_id = body.get("current_intersection_id") or body.get("currentIntersectionId")
        if not veh_id or not curr_id:
            return jsonify({"error": "Both 'emergency_vehicle_id' and 'current_intersection_id' are required."}), 400

        plan = emergency_controller.advance_vehicle(str(veh_id), str(curr_id))
        if not plan:
            return jsonify({"error": f"Active corridor not found for vehicle '{veh_id}'"}), 404
        return jsonify(plan.to_dict()), 200

    @app.route("/api/emergency/release", methods=["POST"])
    def release_emergency_corridor():
        if not request.is_json:
            return jsonify({"error": "Request content-type must be application/json"}), 400
        body = request.get_json(force=True)
        veh_id = body.get("emergency_vehicle_id") or body.get("vehicleId")
        if not veh_id:
            return jsonify({"error": "Field 'emergency_vehicle_id' is required."}), 400

        plan = emergency_controller.release_corridor(str(veh_id))
        if not plan:
            return jsonify({"error": f"No corridor found for vehicle '{veh_id}'"}), 404
        return jsonify(plan.to_dict()), 200

    # =========================================================================
    # Dynamic Traffic Event Endpoints (Phase J)
    # =========================================================================
    event_manager = DynamicEventManager()

    @app.route("/api/events", methods=["POST"])
    def register_event():
        if not request.is_json:
            return jsonify({"error": "Request content-type must be application/json"}), 400
        try:
            body = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Malformed JSON payload"}), 400

        if not isinstance(body, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400

        now = time() if "time" in globals() else datetime.now(timezone.utc).timestamp()
        success, msg, ev = event_manager.register_event(body, current_time=now)
        if not success or ev is None:
            status_code = 400 if "validation" in msg.lower() or "unsupported" in msg.lower() else 422
            return jsonify({
                "event_id": body.get("event_id", body.get("eventId")),
                "accepted": False,
                "validation_status": msg,
                "error": msg,
            }), status_code

        active_status = ev.status_at(now).value
        return jsonify({
            "event_id": ev.event_id,
            "accepted": True,
            "validation_status": "valid",
            "active_status": active_status,
            "effective_impact": {
                "capacity_factor": ev.capacity_factor,
                "demand_multiplier": ev.demand_multiplier,
                "queue_adder": ev.queue_adder,
                "min_pedestrian_green": ev.min_pedestrian_green,
            },
            "affected_intersections": list(ev.affected_intersection_ids),
            "affected_approaches": list(ev.affected_approaches),
            "severity": ev.severity,
            "start_time": ev.start_time,
            "end_time": ev.end_time,
        }), 200

    @app.route("/api/events", methods=["GET"])
    def get_events():
        intersection_id = request.args.get("intersection_id")
        active_only = request.args.get("active_only", "false").lower() in ("true", "1", "yes")
        now = datetime.now(timezone.utc).timestamp()
        events = event_manager.get_all_events(
            active_only=active_only,
            intersection_id=intersection_id,
            current_time=now,
        )
        return jsonify({
            "events": [ev.to_dict() for ev in events],
            "count": len(events),
        }), 200

    @app.route("/api/events/<event_id>", methods=["DELETE"])
    def cancel_event(event_id: str):
        cancelled = event_manager.cancel_event(event_id)
        if not cancelled:
            return jsonify({"error": f"Event '{event_id}' not found"}), 404
        return jsonify({
            "event_id": event_id,
            "status": "cancelled",
            "message": f"Event '{event_id}' successfully cancelled.",
        }), 200

    # =========================================================================
    # Metrics and Evaluation Endpoints (Phase K & L)
    # =========================================================================
    metrics_evaluator = TrafficMetricsEvaluator()

    @app.route("/api/metrics", methods=["POST"])
    def evaluate_metrics_endpoint():
        if not request.is_json:
            return jsonify({"error": "Request content-type must be application/json"}), 400
        try:
            body = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Malformed or invalid JSON body"}), 400

        if not isinstance(body, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400

        raw_list = body.get("states") or body.get("observations") or body.get("intersections")
        if raw_list is None:
            raw_list = [body]
        if not isinstance(raw_list, list) or not raw_list:
            return jsonify({"error": "Payload must contain at least one state or observation"}), 400

        duration = float(body.get("duration_seconds", 60.0))
        decisions_input = body.get("decisions") or {}
        if isinstance(decisions_input, list):
            decisions_map = {
                d.get("intersection_id", d.get("intersectionId")): d
                for d in decisions_input if isinstance(d, dict)
            }
        elif isinstance(decisions_input, dict):
            decisions_map = decisions_input
        else:
            decisions_map = {}

        obs_list = []
        for idx, item in enumerate(raw_list):
            if not isinstance(item, dict):
                return jsonify({"error": f"Item at index {idx} must be an object"}), 400
            try:
                if "queue_lengths" in item and "intersection_id" in item:
                    obs = TrafficObservation.from_dict(item)
                else:
                    state, _ = parse_state_data(item)
                    obs = state.to_observation()
                obs_list.append(obs)
            except Exception as exc:
                return jsonify({"error": f"Error parsing item {idx}: {exc}"}), 400

        net_metrics = metrics_evaluator.evaluate_network(
            observations=obs_list,
            decisions=decisions_map,
            duration_seconds=duration,
            network_id=str(body.get("network_id", "flowq_network")),
        )

        return jsonify(net_metrics.to_dict()), 200

    # =========================================================================
    # Real-World Prototype Perception Endpoints (Phase M)
    # =========================================================================
    perception_service = RealWorldPerceptionService()

    @app.route("/api/perception/config", methods=["GET"])
    def get_perception_config():
        return jsonify({
            "service": "FlowQ Real-World Perception Service",
            "version": "1.0.0",
            "supported_sources": ["image", "video", "camera", "rtsp", "synthetic"],
            "supported_intersections": ["J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8"],
            "supported_classes": ["car", "motorcycle", "bus", "truck"],
            "supported_approaches": ["north", "south", "east", "west"],
            "default_approach_regions": {
                "north": [100.0, 0.0, 300.0, 200.0],
                "south": [100.0, 300.0, 300.0, 500.0],
                "east": [350.0, 150.0, 550.0, 350.0],
                "west": [0.0, 150.0, 80.0, 350.0],
            },
            "hardware_disclaimer": HARDWARE_DISCLAIMER,
            "perception_disclaimer": PERCEPTION_DISCLAIMER,
        }), 200

    @app.route("/api/perception/process", methods=["POST"])
    def process_perception_endpoint():
        if not request.is_json:
            return jsonify({"error": "Request content-type must be application/json"}), 400
        try:
            body = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Malformed or invalid JSON body"}), 400

        if not isinstance(body, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400

        source_type = str(body.get("source_type", "image")).lower().strip()
        intersection_id = str(body.get("intersection_id", "J1")).strip() or "J1"
        source_path = body.get("source_path")
        approach_regions = body.get("approach_regions")
        road_capacity = int(body.get("road_capacity", 100))
        solver = str(body.get("solver", "exact")).lower().strip()
        optimize = bool(body.get("optimize", True))

        if source_type not in ("image", "video", "camera", "rtsp", "synthetic"):
            return jsonify({"error": f"Invalid source_type '{source_type}'. Must be one of: image, video, camera, rtsp, synthetic."}), 400

        try:
            observation = None
            status_meta = {"status": "success"}

            if source_type == "image":
                if source_path:
                    observation = perception_service.process_image(
                        source=source_path,
                        intersection_id=intersection_id,
                        approach_regions=approach_regions,
                    )
                elif "synthetic_data" in body and isinstance(body["synthetic_data"], dict):
                    synth = body["synthetic_data"]
                    observation = TrafficObservation(
                        timestamp=time(),
                        source="synthetic",
                        intersection_id=intersection_id,
                        vehicle_count=int(synth.get("vehicle_count", 0)),
                        tracked_vehicle_count=int(synth.get("tracked_vehicle_count", 0)),
                        average_confidence=float(synth.get("average_confidence", 0.9)),
                        approach_counts=synth.get("approach_counts", {"north": 0, "south": 0, "east": 0, "west": 0}),
                        queue_lengths=synth.get("queue_lengths", {"north": 0, "south": 0, "east": 0, "west": 0}),
                        class_counts=synth.get("class_counts", {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0}),
                        tracking_available=False,
                    )
                else:
                    return jsonify({"error": "source_path or synthetic_data must be provided for image mode."}), 400

            elif source_type == "video":
                if not source_path:
                    return jsonify({"error": "source_path is required for video mode."}), 400
                sampling_rate = int(body.get("frame_sampling_rate", 1))
                max_frames = body.get("max_frames")
                if max_frames is not None:
                    max_frames = int(max_frames)
                observations = perception_service.process_video(
                    video_path=source_path,
                    intersection_id=intersection_id,
                    frame_sampling_rate=sampling_rate,
                    approach_regions=approach_regions,
                    max_frames=max_frames,
                )
                if not observations:
                    return jsonify({"error": "No frames could be processed from the specified video."}), 400
                observation = observations[-1]  # Latest sampled state
                status_meta["frames_processed"] = len(observations)

            elif source_type == "camera":
                camera_index = int(body.get("camera_index", 0))
                obs, cam_status = perception_service.capture_camera_frame(
                    camera_index=camera_index,
                    intersection_id=intersection_id,
                    approach_regions=approach_regions,
                )
                status_meta.update(cam_status)
                if obs is None:
                    return jsonify({
                        "status": "unavailable",
                        "source_type": "camera",
                        "error": cam_status.get("error", "Camera capture failed"),
                        "camera_index": camera_index,
                    }), 503
                observation = obs

            elif source_type == "rtsp":
                rtsp_url = str(body.get("rtsp_url", "")).strip()
                if not rtsp_url:
                    return jsonify({"error": "rtsp_url is required for RTSP mode."}), 400
                timeout_sec = float(body.get("timeout_seconds", 5.0))
                obs, rtsp_status = perception_service.capture_rtsp_frame(
                    rtsp_url=rtsp_url,
                    intersection_id=intersection_id,
                    timeout_seconds=timeout_sec,
                    approach_regions=approach_regions,
                )
                status_meta.update(rtsp_status)
                if obs is None:
                    return jsonify({
                        "status": "unavailable",
                        "source_type": "rtsp",
                        "error": rtsp_status.get("error", "RTSP stream capture failed"),
                        "stream_url": sanitize_rtsp_url(rtsp_url),
                    }), 503
                observation = obs

            elif source_type == "synthetic":
                synth = body.get("synthetic_data", {})
                observation = TrafficObservation(
                    timestamp=time(),
                    source="synthetic",
                    intersection_id=intersection_id,
                    vehicle_count=int(synth.get("vehicle_count", 24)),
                    tracked_vehicle_count=int(synth.get("tracked_vehicle_count", 24)),
                    average_confidence=float(synth.get("average_confidence", 0.92)),
                    approach_counts=synth.get("approach_counts", {"north": 12, "south": 8, "east": 3, "west": 1}),
                    queue_lengths=synth.get("queue_lengths", {"north": 10, "south": 6, "east": 2, "west": 1}),
                    class_counts=synth.get("class_counts", {"car": 18, "motorcycle": 3, "bus": 2, "truck": 1}),
                    tracking_available=True,
                )

            recommendation = None
            if optimize and observation is not None:
                recommendation = perception_service.recommend_signal_timing(
                    observation=observation,
                    solver=solver,
                    road_capacity=road_capacity,
                )

            response_payload = {
                "status": "success",
                "source_type": source_type,
                "intersection_id": intersection_id,
                "meta": status_meta,
                "observation": observation.to_dict() if observation else None,
                "recommendation": recommendation,
                "hardware_disclaimer": HARDWARE_DISCLAIMER,
                "perception_disclaimer": PERCEPTION_DISCLAIMER,
            }
            return jsonify(response_payload), 200

        except (FileNotFoundError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logger.error("Perception endpoint failed: %s", exc)
            return jsonify({"error": f"Perception service error: {exc}"}), 500

<<<<<<< HEAD
=======
    # =========================================================================
    # Live Camera & Video Detection Endpoints (Perception + Dashboard Only)
    # =========================================================================
    live_engine = RealtimeDetectionEngine()

    @app.route("/api/perception/live/start", methods=["POST"])
    def start_live_perception():
        body = request.get_json(force=True) if request.is_json else {}
        if not isinstance(body, dict):
            body = {}

        source_type = str(body.get("source_type", "camera")).lower().strip()
        camera_index = int(body.get("camera_index", 0))
        video_path = body.get("video_path") or body.get("source_path")
        intersection_id = str(body.get("intersection_id", "J1")).strip() or "J1"
        confidence_threshold = float(body.get("confidence_threshold", 0.35))
        inference_fps = float(body.get("inference_fps", 10.0))
        approach_regions = body.get("approach_regions")

        success = live_engine.start(
            source_type=source_type,
            camera_index=camera_index,
            video_path=video_path,
            intersection_id=intersection_id,
            confidence_threshold=confidence_threshold,
            inference_fps=inference_fps,
            approach_regions=approach_regions,
        )

        status_data = live_engine.get_status()
        status_code = 200 if success else (400 if "not found" in str(status_data.get("error", "")).lower() else 503)
        return jsonify(status_data), status_code

    @app.route("/api/perception/live/stop", methods=["POST"])
    def stop_live_perception():
        live_engine.stop()
        return jsonify(live_engine.get_status()), 200

    @app.route("/api/perception/live/status", methods=["GET"])
    def get_live_perception_status():
        return jsonify(live_engine.get_status()), 200

    @app.route("/api/perception/live/stream", methods=["GET"])
    def stream_live_perception():
        return Response(
            live_engine.generate_mjpeg_stream(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/api/perception/live/frame", methods=["GET"])
    def get_live_perception_frame():
        jpeg_bytes = live_engine.get_latest_jpeg()
        return Response(jpeg_bytes, mimetype="image/jpeg")

>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
    return app
