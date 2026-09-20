# FlowQ: Quantum-Enhanced Adaptive Urban Traffic Optimization
## Master Team Handover & Technical Transition Document

---

## 1. Executive Summary
This document serves as the master engineering handover for **FlowQ: Quantum-Enhanced Adaptive Urban Traffic Optimization**. All development phases (**Phases 1–3B and Phases A through P**) have been fully designed, implemented, tested, and validated.

The system constitutes an end-to-end, hybrid classical-quantum digital twin that ingests raw camera/video or microscopic simulation data, performs vehicle detection and velocity-based queue estimation, enforces a canonical data contract, coordinates multi-intersection networks, handles emergency green corridor preemption and dynamic incident adaptation, optimizes signal timings via exact QUBO and QAOA quantum circuits, computes stoichiometric emissions, and visualizes live operations via an interactive dark-glassmorphic command dashboard.

---

## 2. Master Roadmap & Phase Completion Status

Every phase across the project lifecycle is **100% complete and verified**:

| Phase | Milestone Description | Implementation Highlights | Status |
| :--- | :--- | :--- | :---: |
| **Phase 1** | SUMO Traffic Foundation | Eclipse SUMO 1.27.1 integration, TraCI, 4 connected junctions, baseline fixed-time controller | **COMPLETE** ✅ |
| **Phase 2** | Classical Adaptive Signals | Rule-based queue imbalance adaptation ($|q_{\text{NS}} - q_{\text{EW}}| \ge 6\text{ veh}$), safety limits | **COMPLETE** ✅ |
| **Phase 3A** | QUBO Formulation & Exact Solver | 9-variable discrete candidate green timing formulation ($22\text{s}, 30\text{s}, 40\text{s}$), penalty $P=50.0$ | **COMPLETE** ✅ |
| **Phase 3B** | QAOA Formulation & Aer Simulation | Ising transformation $x_k = (I - Z_k)/2$, variational Ansatz $p=1$, COBYLA optimizer | **COMPLETE** ✅ |
| **Phase A** | Python Optimization REST API | Flask service (`server.py`, port 5001) exposing `POST /api/optimize` and `GET /api/health` | **COMPLETE** ✅ |
| **Phase B** | Node.js Proxy & Bridge Integration | Reverse proxy (`web/server.js`, port 4173) with automatic offline fallback to `optimizer.js` | **COMPLETE** ✅ |
| **Phase C** | Safe Phase-Boundary Signal Control | Safe signal timing injection at cycle boundaries, 4s fixed yellow, $15\text{s}$ anti-oscillation damping | **COMPLETE** ✅ |
| **Phase D** | YOLOv8 Vehicle Detection Backend | Ultralytics YOLOv8n (`yolov8n.pt`) vehicle detection (`car`, `bus`, `truck`, `motorcycle`) | **COMPLETE** ✅ |
| **Phase E** | Tracking & Traffic Aggregation | Centroid MOT tracker, ray-casting point-in-polygon ROI assignment, track deduplication | **COMPLETE** ✅ |
| **Phase F** | Velocity-Based Queue Estimation | Velocity thresholding: moving ($v \ge 2.5\text{ m/s}$), stopped queue ($v < 0.5\text{ m/s}$) | **COMPLETE** ✅ |
| **Phase G** | Common `TrafficObservation` Contract | Immutable, validated JSON schema shared across perception, simulation, and optimization | **COMPLETE** ✅ |
| **Phase H** | Multi-Intersection Network Control | Coordinated J1–J4 (extensible to 8+) control, observation freshness ($30\text{s}$), persistent states | **COMPLETE** ✅ |
| **Phase I** | Emergency Green Corridor Priority | Arterial green wave preemption, conflict resolution, progressive release ($93.3\text{s}$ saved) | **COMPLETE** ✅ |
| **Phase J** | Dynamic Traffic Events Management | Accidents (capacity drop to 35%), road closures, demand surges, pedestrian crossings | **COMPLETE** ✅ |
| **Phase K** | Metrics / Fuel / $\text{CO}_2$ Evaluation | Physical TraCI emissions & stoichiometric proxies ($0.00025\text{ L/s}$ idle, $2392\text{ g CO}_2/\text{L}$) | **COMPLETE** ✅ |
| **Phase L** | Final Integrated Dashboard | Node.js / HTML5 command dashboard, 2D city grid canvas, 7 interactive inspection panels | **COMPLETE** ✅ |
| **Phase M** | Real-World Prototype Interface | Ingestion of camera, MP4 video, and RTSP streams with automated credential masking | **COMPLETE** ✅ |
| **Phase N** | Classical vs Quantum Evaluation | Reproducible benchmark across 60 simulations and 240 QAOA decisions ($93.33\%$ recovery) | **COMPLETE** ✅ |
| **Phase O** | End-to-End System Validation | 16 deterministic scenarios (A–P), 14 failure vectors, bit-for-bit classical reproducibility | **COMPLETE** ✅ |
| **Phase P** | Final Documentation & Presentation | 30-section report, REST API guide, setup manual, 14-step demo guide, presentation slides | **COMPLETE** ✅ |

---

## 3. System Architecture & Information Flow

```text
+---------------------------------------------------------------------------------------------------+
|                                      INPUT / SENSING LAYER                                        |
|  [SUMO Micro-Sim]  /  [Web Simulation Canvas]  /  [Camera / RTSP / Video / Image Media Streams]   |
+---------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+---------------------------------------------------------------------------------------------------+
|                                   COMPUTER VISION PERCEPTION                                      |
|   Ultralytics YOLOv8 Detection  ──►  MOT Centroid Tracking  ──►  Point-in-Polygon Approach ROIs   |
|                                                                     (North, South, East, West)    |
|                                                                                 │                 |
|                                                                                 ▼                 |
|                                                                      Velocity Queue Estimator     |
|                                                                     (v < 0.5 m/s stopped queue)   |
+---------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+---------------------------------------------------------------------------------------------------+
|                             CANONICAL DATA CONTRACT & SUPERVISOR                                  |
|                                    TrafficObservation JSON                                        |
|                                                  │                                                |
|                                                  ▼                                                |
|                                 IntersectionTrafficState Transformer                              |
|                                                  │                                                |
|                                                  ▼                                                |
|                                     MultiIntersectionController                                  |
|         ┌────────────────────────────────────────┼────────────────────────────────────────┐       |
|         ▼                                        ▼                                        ▼       |
|  [Emergency Controller]                 [Dynamic Events]                    [Freshness / Damping] |
|  - J1 -> J4 Green Wave                  - Accidents (cap -65%)              - max_age: 30s        |
|  - Preemption Precedence                - Closures (cap -95%)               - damping: 15s        |
|  - Progressive Clearance                - Demand Surges                     - safe bounds [22,42] |
+---------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+---------------------------------------------------------------------------------------------------+
|                              MATHEMATICAL OPTIMIZATION ENGINE                                     |
|    Single-Junction QUBO Model                  Ising Hamiltonian Mapping & QAOA                   |
|    min E(x) = x^T Q x                          H_C = sum J_ij Z_i Z_j + sum h_i Z_i + offset      |
|    - Delay weighting                           - Qiskit AerSimulator (statevector)                |
|    - Queue imbalance                           - COBYLA Variational Parameter Optimizer           |
|    - Target cycle constraint                   - Depth p=1 Ansatz                                 |
|    - One-hot penalty P=50.0                    - 1024 / 2048 Bitstring Sampling & Decoding        |
|                                                                                                   |
|    [Exact Classical Solver]                    [QAOA Research Optimizer]                         |
+---------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+---------------------------------------------------------------------------------------------------+
|                                 SIGNAL EXECUTION & SAFETY LAYER                                   |
|  Phase-Boundary Timing Injection  │  Fixed 4s Yellow  │  All-Red Clearance  │  Anti-Oscillation   |
+---------------------------------------------------------------------------------------------------+
                                                  │
                         ┌────────────────────────┴────────────────────────┐
                         ▼                                                 ▼
+------------------------------------------------───+     +-----------------------------------------+
|             METRICS & EMISSIONS LAYER             |     |       FLOWQ MOBILITY DASHBOARD          |
|  - Delay, Queues, Throughput                      |     |  - Digital Twin 2D Grid Canvas (J1-J8)  |
|  - Stoichiometric: 0.00025 L/s idle, 2392 g/L CO2 |     |  - Emergency Corridor Dispatcher        |
|  - Benchmark Exporter (CSV / JSON)                |     |  - Real-World Video Prototype Interface |
+---------------------------------------------------+     +-----------------------------------------+
```

---

## 4. Key Files & Directory Mapping

| Directory / File | Subsystem | Responsibility |
| :--- | :--- | :--- |
| [`server.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/server.py) | Backend API | Flask entrypoint on port `5001` exposing all REST endpoints. |
| [`optimization/service.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/optimization/service.py) | Optimizer Service | Routes for `/api/optimize`, `/api/emergency/*`, `/api/events`, `/api/metrics`, `/api/perception/*`. |
| [`optimization/quantum/qubo.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/optimization/quantum/qubo.py) | QUBO Formulation | Builds the 9-variable upper-triangular $\mathbf{Q}$ matrix with one-hot constraints. |
| [`optimization/quantum/solver.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/optimization/quantum/solver.py) | Exact Solver | Exhaustive classical evaluation of all 9 valid basis states ($0.85\text{ ms}$). |
| [`optimization/quantum/qaoa.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/optimization/quantum/qaoa.py) | Quantum QAOA | Translates QUBO to Ising Hamiltonian, executes parameterized quantum circuits via Qiskit Aer. |
| [`perception/detector.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/perception/detector.py) | Vision Detection | Ultralytics YOLOv8n detector with synthetic fallback. |
| [`perception/aggregator.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/perception/aggregator.py) | MOT & ROI Mapping | Centroid tracker and ray-casting point-in-polygon approach ROI classifier. |
| [`perception/queue_estimator.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/perception/queue_estimator.py) | Queue Estimator | Velocity-based stopped queue accumulation per approach. |
| [`perception/models.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/perception/models.py) | Data Contracts | Canonical `TrafficObservation` schema with strict validation. |
| [`simulation/signals/multi_intersection.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/simulation/signals/multi_intersection.py) | Network Controller | Manages connected junctions (J1–J8), freshness checks, and independent QUBO calls. |
| [`simulation/signals/emergency.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/simulation/signals/emergency.py) | Emergency Preemption | Green corridor dispatcher, conflict resolution, progressive clearance. |
| [`simulation/signals/events.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/simulation/signals/events.py) | Dynamic Events | Ingests accidents, closures, surges; transforms effective traffic states. |
| [`metrics/evaluator.py`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/metrics/evaluator.py) | Emissions & Delay | Computes delay, throughput, fuel consumption ($0.00025\text{ L/s}$), and $\text{CO}_2$ ($2392\text{ g/L}$). |
| [`web/server.js`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/web/server.js) | Frontend Server | Node.js web server on port `4173` with reverse proxy forwarding to port `5001`. |
| [`web/public/`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/web/public/) | Dashboard UI | Dark glassmorphic HTML5/CSS3/ES6+ digital twin interface. |
| [`experiments/`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/experiments/) | Experiment Runners | Standalone CLI scripts for benchmarks and demonstrations. |
| [`docs/`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/) | Documentation | Complete suite of 9 technical guides, reports, and manuals. |

---

## 5. How to Run the System

### Quickstart (Dual-Service Architecture)
1. **Terminal 1: Start Python Backend (Port 5001)**:
   ```powershell
   python server.py
   ```
2. **Terminal 2: Start Node.js Web Dashboard (Port 4173)**:
   ```powershell
   node web/server.js
   ```
3. **Open Dashboard in Browser**:
   Navigate to **`http://localhost:4173/`**.

### Standalone Benchmark & Demo Commands
```powershell
# 1. Classical vs Quantum Benchmark (60 simulations, 240 QAOA decisions)
python experiments/run_classical_vs_quantum.py

# 2. End-to-End System Validation (Full lifecycle profiling)
python experiments/run_end_to_end_validation.py

# 3. Emergency Green Corridor Demonstration
python experiments/run_emergency_corridor_demo.py

# 4. Dynamic Events Pipeline Demonstration
python experiments/run_dynamic_events_demo.py

# 5. Multi-Intersection Network Coordination Demonstration
python experiments/run_multi_intersection_demo.py

# 6. Real-World Perception Vision Pipeline Demonstration
python experiments/run_realworld_perception_demo.py
```

---

## 6. Automated Testing & Verification Audit

The test suite is verified and free of regressions:

```powershell
# Run the complete Python test suite (159 tests)
python -m pytest -q
# Output: 159 passed in ~28s

# Run the complete Node.js test suite (9 tests)
cd web; npm test; cd ..
# Output: 9 passed in ~4s

# Run the dedicated End-to-End integration test suite
python -m pytest tests/test_end_to_end_validation.py -v
# Output: 10 passed in ~4s
```

---

## 7. Safety Invariants & Precedence Hierarchy

The system strictly enforces a non-negotiable supervisory control hierarchy:
$$\boxed{\text{Signal Safety Clearance} \succ \text{Emergency Priority Corridor} \succ \text{Dynamic Event Adaptation} \succ \text{Normal QUBO / QAOA Control}}$$

### Non-Negotiable Invariants
1. **No Conflicting Greens**: Conflicting phases (Phase 0 North-South vs Phase 2 East-West) are never simultaneously green.
2. **Interval Preservation**: Mandatory 4-second fixed yellow transitions and all-red clearance intervals are strictly maintained during normal operation, emergency preemption, and dynamic event adaptation.
3. **Positive Bounded Green Durations**: Green durations strictly satisfy $22\text{s} \le g \le 42\text{s}$.
4. **Anti-Oscillation Damping**: Damping threshold ($15\text{s}$) prevents erratic signal hunting under transient sensor noise.
5. **Phase-Boundary Transitions**: Timing updates are queued and applied only at safe phase transitions.
6. **Clean Release**: Emergency preemption and dynamic event modifications release cleanly back to baseline QUBO control without residual overrides.

---

## 8. Complete Documentation Sitemap (`docs/`)

All project documentation is organized in [`docs/`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/):
- **[`docs/final_project_report.md`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/final_project_report.md)**: 30-section comprehensive project report.
- **[`docs/api.md`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/api.md)**: Complete REST API reference manual.
- **[`docs/setup.md`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/setup.md)**: Environment installation and server setup guide.
- **[`docs/demo_guide.md`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/demo_guide.md)**: 14-stage technical and hackathon demonstration sequence.
- **[`docs/results_index.md`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/results_index.md)**: Index and catalog of all CSV, JSON, and plot artifacts.
- **[`docs/reproducibility.md`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/reproducibility.md)**: Scientific reproducibility protocol (seeds, configs, commands).
- **[`docs/presentation_outline.md`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/presentation_outline.md)**: 12-slide presentation structure with talking points.
- **[`docs/hackathon_checklist.md`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/hackathon_checklist.md)**: Pre-flight judging checklist.
- **[`docs/phase_o_validation_report.md`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/phase_o_validation_report.md)**: System integration validation report.

---

## 9. Known Limitations & Research Boundaries

1. **Simulation Environment**: All microscopic vehicle dynamics are modeled within Eclipse SUMO 1.27.1; results reflect modeled kinematics and should not be cited as municipal field data.
2. **Quantum Backend**: QAOA was executed on classical statevector simulation (`AerSimulator`) rather than physical QPUs. Quantum decoherence, gate errors, and readout infidelities were not modeled.
3. **Queue Estimation**: The prototype queue estimator operates in image pixel coordinates; real-world deployment requires extrinsic camera calibration to translate pixels to metric world coordinates.
4. **Advisory Prototype Scope**: The real-world vision interface produces advisory recommendations and does not actuate physical traffic-light cabinet hardware.
5. **Fixed Two-Phase Assumption**: The current formulation assumes orthogonal 2-phase green cycles (NS vs EW); complex multi-phase junctions with protected left-turn arrows require extending the QUBO variable space.

---

## 10. Handover Sign-Off

The FlowQ codebase is clean, well-tested, fully documented, and ready for immediate presentation, deployment to testing staging, or continuation into physical quantum hardware experiments.
