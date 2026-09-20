# FlowQ REST API Reference Manual

The FlowQ backend exposes a unified REST API via Flask on port `5001` (proxied by the Node.js frontend on port `4173`). All request and response bodies use standard `application/json` payloads.

---

## 1. System Health & Status

### `GET /api/health`
Checks backend operational status, available optimization solvers, and model readiness.

- **Request**: No body or query parameters required.
- **Response `200 OK`**:
```json
{
  "ok": true,
  "service": "FlowQ Canonical Python Optimizer",
  "solvers": ["exact", "qaoa"],
  "status": "ready"
}
```

---

## 2. Signal Optimization API

### `POST /api/optimize`
Performs mathematical signal timing optimization for either a single intersection or a coordinated multi-intersection batch using exact QUBO or QAOA.

#### A. Single Intersection Request
```json
{
  "intersection_id": "J1",
  "solver": "exact",
  "queue_lengths": {
    "north": 14,
    "south": 12,
    "east": 3,
    "west": 3
  },
  "vehicle_count": 32,
  "road_capacity": 100,
  "current_signal_phase": 0
}
```

- **Response `200 OK`**:
```json
{
  "intersection_id": "J1",
  "solver": "exact",
  "phase_0_green_seconds": 40,
  "phase_2_green_seconds": 22,
  "objective": 9.8587,
  "valid": true
}
```

#### B. Multi-Intersection Batch Request
```json
{
  "solver": "exact",
  "states": [
    {
      "intersection_id": "J1",
      "vehicle_count": 32,
      "queue_lengths": { "north": 16, "south": 10, "east": 1, "west": 1 }
    },
    {
      "intersection_id": "J2",
      "vehicle_count": 36,
      "queue_lengths": { "north": 1, "south": 1, "east": 18, "west": 12 }
    }
  ]
}
```

- **Response `200 OK`**:
```json
{
  "method": "QUBO exact",
  "solver": "exact",
  "results": [
    {
      "intersection_id": "J1",
      "phase_0_green_seconds": 40,
      "phase_2_green_seconds": 22,
      "objective": 9.8587,
      "valid": true,
      "intersectionId": "J1",
      "nsGreen": 40,
      "ewGreen": 22
    },
    {
      "intersection_id": "J2",
      "phase_0_green_seconds": 22,
      "phase_2_green_seconds": 40,
      "objective": 11.8584,
      "valid": true,
      "intersectionId": "J2",
      "nsGreen": 22,
      "ewGreen": 40
    }
  ],
  "decisions": [ ... ],
  "generatedAt": "2026-09-20T01:00:00.000000Z"
}
```

- **Validation & Error Codes**:
  - `400 Bad Request`: Missing `intersection_id`, negative vehicle counts/queues, or malformed JSON.
  - `422 Unprocessable Entity`: QAOA convergence failure or solver runtime error.

---

## 3. Emergency Green Corridor Priority Endpoints

### `POST /api/emergency/corridor`
Requests priority green wave preemption along a specified arterial intersection route.

- **Request**:
```json
{
  "emergency_vehicle_id": "AMB_001",
  "current_intersection_id": "J1",
  "destination_intersection_id": "J4",
  "route": ["J1", "J2", "J3", "J4"],
  "priority_level": "critical",
  "timestamp": 1789840200.0
}
```

- **Response `200 OK`**:
```json
{
  "emergency_vehicle_id": "AMB_001",
  "corridor_status": "active",
  "status": "active",
  "current_state": "active",
  "affected_intersections": ["J1", "J2", "J3", "J4"],
  "requested_approach": "south",
  "requested_phase": 0,
  "temporary_timing_decisions": {
    "J1": { "intersection_id": "J1", "priority_approach": "south", "priority_phase": 0, "priority_green_seconds": 40, "non_priority_green_seconds": 22, "status": "active" },
    "J2": { "intersection_id": "J2", "priority_approach": "west", "priority_phase": 2, "priority_green_seconds": 40, "non_priority_green_seconds": 22, "status": "active" },
    "J3": { "intersection_id": "J3", "priority_approach": "west", "priority_phase": 2, "priority_green_seconds": 40, "non_priority_green_seconds": 22, "status": "active" },
    "J4": { "intersection_id": "J4", "priority_approach": "west", "priority_phase": 2, "priority_green_seconds": 40, "non_priority_green_seconds": 22, "status": "active" }
  },
  "validation_result": "Emergency corridor activated successfully",
  "valid": true,
  "metrics": {
    "emergency_vehicle_id": "AMB_001",
    "route": ["J1", "J2", "J3", "J4"],
    "intersections_affected": 4,
    "signal_overrides_applied": 4,
    "activation_duration_seconds": 0.0,
    "estimated_travel_time_seconds": 60.0
  }
}
```

- **Error Codes**:
  - `400 Bad Request`: Missing vehicle ID or route, disconnected route path.
  - `422 Unprocessable Entity`: Preempted by higher-priority emergency request.

---

### `GET /api/emergency/corridor`
Queries active corridors or retrieves specific vehicle status.

- **Query Parameters**:
  - `vehicle_id` (optional): Filter by vehicle ID.
- **Response `200 OK`**:
```json
{
  "active_corridors": {
    "AMB_001": { ... }
  },
  "count": 1
}
```

---

### `POST /api/emergency/advance`
Updates vehicle position as it traverses the corridor, immediately releasing traversed junctions back to QUBO optimization.

- **Request**:
```json
{
  "emergency_vehicle_id": "AMB_001",
  "current_intersection_id": "J2"
}
```

- **Response `200 OK`**:
```json
{
  "emergency_vehicle_id": "AMB_001",
  "current_intersection_id": "J2",
  "corridor_status": "active",
  "intersection_plans": {
    "J1": { "intersection_id": "J1", "status": "released" },
    "J2": { "intersection_id": "J2", "status": "active" }
  }
}
```

---

### `POST /api/emergency/release`
Manually terminates an active corridor and restores baseline QUBO control to all junctions.

- **Request**:
```json
{
  "emergency_vehicle_id": "AMB_001"
}
```

- **Response `200 OK`**:
```json
{
  "emergency_vehicle_id": "AMB_001",
  "corridor_status": "released",
  "status": "released"
}
```

---

## 4. Dynamic Events API

### `POST /api/events`
Registers a dynamic incident (accident, road closure, surge, pedestrian crowd) affecting road capacities or demand.

- **Request**:
```json
{
  "event_id": "ACC_J2_01",
  "event_type": "accident",
  "affected_intersection_ids": ["J2"],
  "affected_approaches": ["east"],
  "severity": "high",
  "capacity_factor": 0.35,
  "queue_adder": 18,
  "start_time": 1789840200.0,
  "end_time": 1789840500.0
}
```

- **Response `200 OK`**:
```json
{
  "event_id": "ACC_J2_01",
  "accepted": true,
  "validation_status": "valid",
  "active_status": "active",
  "effective_impact": {
    "capacity_factor": 0.35,
    "demand_multiplier": 1.0,
    "queue_adder": 18,
    "min_pedestrian_green": 0
  },
  "affected_intersections": ["J2"],
  "affected_approaches": ["east"],
  "severity": "high",
  "start_time": 1789840200.0,
  "end_time": 1789840500.0
}
```

---

### `GET /api/events`
Lists registered dynamic events with optional filters.

- **Query Parameters**:
  - `intersection_id` (optional): Filter by intersection ID (e.g. `?intersection_id=J2`).
  - `active_only` (optional): Return only active events (`?active_only=true`).
- **Response `200 OK`**:
```json
{
  "events": [ ... ],
  "count": 1
}
```

---

### `DELETE /api/events/<event_id>`
Cancels an active or scheduled dynamic event, instantly restoring normal approach capacity.

- **Response `200 OK`**:
```json
{
  "event_id": "ACC_J2_01",
  "status": "cancelled",
  "message": "Event 'ACC_J2_01' successfully cancelled."
}
```

---

## 5. Metrics & Sustainability API

### `POST /api/metrics`
Evaluates system delay, queues, throughput, fuel consumption, and $\text{CO}_2$ emissions over a specified time duration.

- **Request**:
```json
{
  "network_id": "flowq_network",
  "duration_seconds": 60.0,
  "observations": [
    {
      "intersection_id": "J1",
      "vehicle_count": 32,
      "queue_lengths": { "north": 14, "south": 12, "east": 3, "west": 3 }
    }
  ],
  "decisions": {
    "J1": { "phase_0_green_seconds": 40, "phase_2_green_seconds": 22 }
  }
}
```

- **Response `200 OK`**:
```json
{
  "network_id": "flowq_network",
  "evaluation_duration_seconds": 60.0,
  "total_waiting_time_seconds": 240.0,
  "average_waiting_time_seconds": 7.5,
  "total_queue_length_vehicles": 32,
  "average_queue_length_vehicles": 8.0,
  "maximum_queue_length_vehicles": 14,
  "completed_vehicles_count": 28,
  "throughput_vehicles_per_hour": 1680.0,
  "total_fuel_consumption_liters": 0.524,
  "total_co2_emissions_grams": 1253.4,
  "per_intersection_metrics": { ... }
}
```

---

## 6. Real-World Perception API

### `GET /api/perception/config`
Retrieves perception configuration, default ROIs, and prototype disclaimers.

- **Response `200 OK`**:
```json
{
  "service": "FlowQ Real-World Perception Service",
  "version": "1.0.0",
  "supported_sources": ["image", "video", "camera", "rtsp", "synthetic"],
  "supported_intersections": ["J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8"],
  "hardware_disclaimer": "FlowQ prototype produces advisory signal recommendations and does not actuate physical traffic-light hardware.",
  "perception_disclaimer": "Prototype queue estimation is pixel-displacement based and subject to optical occlusion."
}
```

---

### `POST /api/perception/process`
Ingests media, runs YOLOv8 vehicle detection, multi-object tracking, queue estimation, and produces prototype signal recommendations.

- **Request**:
```json
{
  "source_type": "image",
  "source_path": "data/synthetic/sample_frame.jpg",
  "intersection_id": "J1",
  "solver": "exact",
  "optimize": true
}
```

- **Response `200 OK`**:
```json
{
  "status": "success",
  "source_type": "image",
  "intersection_id": "J1",
  "observation": {
    "timestamp": 1789840200.0,
    "source": "yolo_tracker",
    "intersection_id": "J1",
    "vehicle_count": 8,
    "tracked_vehicle_count": 8,
    "average_confidence": 0.92,
    "approach_counts": { "north": 4, "south": 2, "east": 1, "west": 1 },
    "queue_lengths": { "north": 3, "south": 2, "east": 1, "west": 0 },
    "class_counts": { "car": 6, "motorcycle": 1, "bus": 1, "truck": 0 },
    "tracking_available": true
  },
  "recommendation": {
    "intersection_id": "J1",
    "solver": "exact",
    "phase_0_green_seconds": 40,
    "phase_2_green_seconds": 22,
    "objective": 5.4211,
    "valid": true,
    "hardware_notice": "Advisory recommendation only."
  }
}
```
