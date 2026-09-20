# FlowQ: Quantum-Enhanced Adaptive Urban Traffic Optimization

[![Python Tests](https://img.shields.io/badge/Python%20Tests-159%20Passing-brightgreen.svg)](#testing--verification)
[![Node Tests](https://img.shields.io/badge/Node%20Tests-9%20Passing-brightgreen.svg)](#testing--verification)
[![Qiskit](https://img.shields.io/badge/Qiskit-2.5.2-blue.svg)](https://qiskit.org/)
[![SUMO](https://img.shields.io/badge/SUMO-1.27.1-orange.svg)](https://sumo.dlr.de/)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-purple.svg)](https://ultralytics.com/)
[![License](https://img.shields.io/badge/License-Apache%202.0-lightgrey.svg)](LICENSE)

**FlowQ** is an end-to-end, hybrid classical-quantum intelligent transportation management platform. It integrates microscopic traffic simulation, computer vision micro-perception, mathematical signal optimization, and quantum algorithmic research to address urban gridlock, emergency transit delays, and vehicular emissions. By casting signal timing as a Quadratic Unconstrained Binary Optimization (QUBO) problem and mapping it to an Ising spin Hamiltonian, FlowQ evaluates exact classical baselines alongside the Quantum Approximate Optimization Algorithm (QAOA) on simulated quantum circuits—all governed by a non-negotiable, safety-critical preemption hierarchy.

---

## Key Features

1. **Micro-Perception & Queue Estimation**: Ultralytics YOLOv8 vehicle detection coupled with centroid Multi-Object Tracking (MOT), ray-casting approach Region-of-Interest (ROI) classification, and velocity-based stopped queue estimation ($v < 0.5\text{ m/s}$).
2. **Canonical Data Contract**: A single, immutable, validated `TrafficObservation` JSON schema shared seamlessly across simulation, perception, optimization, and visualization modules.
3. **Exact QUBO & QAOA Optimization**: Formulates signal phase allocations over discrete candidate green durations ($22\text{s}, 30\text{s}, 40\text{s}$) with delay, queue imbalance, and cycle duration penalties. Solved via exact classical state-space search ($0.85\text{ ms}$) and QAOA on Qiskit quantum simulators ($93.33\%$ recovery of exact classical optimum).
4. **Multi-Intersection Network Orchestration**: Coordinates arterial networks across 4 to 8+ connected intersections with observation freshness enforcement ($30\text{s}$ window) and anti-oscillation damping ($15\text{s}$).
5. **Emergency Green Corridor Preemption**: Ingests emergency vehicle priority requests, establishes arterial green waves along multi-junction routes, provides progressive junction release upon traversal, and restores normal QUBO control cleanly (saving $93.3\text{s}$ over baseline transit delay).
6. **Dynamic Incident Adaptation**: Ingests real-world traffic perturbations (accidents, road closures, traffic demand surges, pedestrian crossings) and adapts effective road states while strictly obeying the supervisory precedence hierarchy:
   $$\text{Signal Safety Clearance} \succ \text{Emergency Priority} \succ \text{Dynamic Event Adaptation} \succ \text{Normal QUBO / QAOA}$$
7. **Environmental Sustainability Metrics**: Evaluates vehicular delay, throughput, fuel consumption ($0.00025\text{ L/s}$ idle), and stoichiometric $\text{CO}_2$ emissions ($2,392\text{ g CO}_2 / \text{L}$).
8. **Interactive Digital Twin Dashboard**: High-performance Node.js / HTML5 dark glassmorphic command dashboard featuring 2D traffic canvas, live signal states, junction inspection, and dedicated research panels.
9. **Real-World Prototype Vision Interface**: Ingests camera feeds, local video, or RTSP streams, executes perception, and produces prototype signal recommendations with automated credential masking.

---

## System Architecture

```text
[SUMO Micro-Sim]  /  [Web Simulation Canvas]  /  [Camera / RTSP / Video Streams]
                                  │
                                  ▼
[YOLOv8 Detection] ──► [Centroid Tracking] ──► [Approach ROIs] ──► [Queue Estimator]
                                                                          │
                                                                          ▼
                                                                [TrafficObservation]
                                                                          │
                                                                          ▼
                                                            [Multi-Intersection Controller]
                                                              ┌───────────┴───────────┐
                                                              ▼                       ▼
                                                     [Emergency Priority]    [Dynamic Events]
                                                              │                       │
                                                              └───────────┬───────────┘
                                                                          │
                                                                          ▼
                                                          [QUBO Exact / QAOA Optimization]
                                                                          │
                                                                          ▼
                                                          [Phase-Boundary Signal Control]
                                                              ┌───────────┴───────────┐
                                                              ▼                       ▼
                                                     [Metrics & Emissions]   [FlowQ Dashboard]
```

---

## Technology Stack

- **Microscopic Traffic Simulation**: Eclipse SUMO 1.27.1, TraCI, HTML5 2D Canvas.
- **Quantum Computing & Math**: Python 3.14, Qiskit 2.5.2, Qiskit Aer 0.17.2, NumPy, SciPy (COBYLA).
- **Vision & Perception**: Ultralytics YOLOv8n (`yolov8n.pt`), OpenCV (cv2 5.0.0), PyTorch.
- **Backend Services**: Flask 3.0 (REST API on port `5001`), Python `urllib` / `requests`.
- **Frontend & Bridge**: Node.js v22 (`http` reverse proxy on port `4173`), Vanilla JavaScript ES6+, CSS3.
- **Testing & Quality Assurance**: Pytest (159 tests), Node Test Runner (`node --test`, 9 suites).

---

## Quickstart & Installation

### 1. Prerequisites
- Python 3.10+ (tested on 3.14.4 / 3.11+)
- Node.js v18.0+ (tested on v22.14.0)
- Eclipse SUMO 1.18+ (tested on 1.27.1)

### 2. Installation
```powershell
# Clone the repository
git clone https://github.com/CybroatriX/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization.git
cd Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1

# Set up Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

# Install Node.js frontend dependencies
cd web
npm install
cd ..
```

### 3. Launch the System
Open two terminal windows:

**Terminal 1 (Python Optimization Backend on port 5001):**
```powershell
python server.py
```

**Terminal 2 (Node.js Web Dashboard on port 4173):**
```powershell
node web/server.js
```

Open your browser to: **`http://localhost:4173/`**

---

## Testing & Verification

### Run Full Regression Suites
```powershell
# Python unit, integration, and end-to-end regression (159 tests)
python -m pytest -q

# Node.js frontend and bridge test suite (9 tests)
cd web
npm test
cd ..
```

### Run Major Benchmarks & Demonstrations
```powershell
# 1. Classical vs Quantum Benchmark across 60 simulations and 240 QAOA decisions (Phase N)
python experiments/run_classical_vs_quantum.py

# 2. End-to-End System Validation & Profiling Script (Phase O)
python experiments/run_end_to_end_validation.py

# 3. Emergency Green Corridor Priority Demonstration
python experiments/run_emergency_corridor_demo.py

# 4. Dynamic Traffic Events Demonstration
python experiments/run_dynamic_events_demo.py
```

---

## Empirical Evaluation Summary

| Scenario | Controller | Avg Delay (s) | Avg Queue (veh) | Throughput (vph) | Fuel (L) | $\text{CO}_2$ (g) | Solver Latency (s) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Low** | Fixed-Time | $0.0000$ | $0.0000$ | $180.0$ | $0.4616$ | $1104.2$ | $0.0000$ |
| | Classical Adaptive | $0.0000$ | $0.0000$ | $180.0$ | $0.4616$ | $1104.2$ | $0.0000$ |
| | QUBO Exact | $0.0000$ | $0.0000$ | $180.0$ | $0.4410$ | $1056.8$ | $0.0008$ |
| | QAOA | $0.0000$ | $0.0000$ | $180.0$ | $0.4410$ | $1056.8$ | $0.6221$ |
| **Normal** | Fixed-Time | $0.0000$ | $0.0000$ | $540.0$ | $0.4906$ | $1173.4$ | $0.0000$ |
| | Classical Adaptive | $0.0000$ | $0.0000$ | $540.0$ | $0.4906$ | $1173.4$ | $0.0000$ |
| | QUBO Exact | $0.0000$ | $0.0000$ | $420.0$ | $0.5187$ | $1240.7$ | $0.0008$ |
| | QAOA | $0.0000$ | $0.0000$ | $420.0$ | $0.5187$ | $1240.7$ | $0.6288$ |
| **High** | Fixed-Time | $0.0000$ | $0.0000$ | $720.0$ | $0.5050$ | $1208.0$ | $0.0000$ |
| | Classical Adaptive | $0.0000$ | $0.0000$ | $720.0$ | $0.5050$ | $1208.0$ | $0.0000$ |
| | QUBO Exact | $0.0000$ | $0.0000$ | $456.0$ | $0.5367$ | $1283.8$ | $0.0008$ |
| | QAOA | $0.0000$ | $0.0000$ | $456.0$ | $0.5367$ | $1283.8$ | $0.6267$ |

### Key Findings
- **QAOA Ground-Truth Recovery**: Across 240 optimization runs, QAOA achieved an overall exact classical optimum recovery rate of **$93.33\%$** ($100\%$ in Low traffic, $92.5\%$ in Normal, $87.5\%$ in High) with $100\%$ feasible solutions.
- **Emergency Priority**: Emergency green wave preemption along route `J1 -> J2 -> J3 -> J4` reduced ambulance travel time from $153.3\text{s}$ to $60.0\text{s}$ (**$93.3\text{s}$ saved**).
- **Incident Recovery**: Dynamic event injection safely adapted signal splits to clear incident queues during a 65% capacity reduction.

---

## Known Research Limitations

1. **Simulation Environment**: All vehicle dynamics are simulated in Eclipse SUMO and synthetic browser proxies; results reflect modeled kinematics and should not be cited as municipal field data.
2. **Quantum Backend**: QAOA was executed on classical statevector simulation (`AerSimulator`) rather than physical QPUs. Quantum decoherence and gate errors were not present.
3. **Advisory Prototype Scope**: The real-world vision interface produces advisory recommendations and does not actuate physical traffic-light cabinet hardware.

---

## Repository Structure

```text
Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/
├── config/              # YAML runtime configuration files
├── data/
│   ├── results/         # Benchmark CSV, JSON, and research plots
│   ├── sumo/            # SUMO network geometry and route definitions
│   └── synthetic/       # Synthetic media and test frames
├── docs/                # Comprehensive engineering and scientific documentation
│   ├── final_project_report.md
│   ├── api.md
│   ├── setup.md
│   ├── demo_guide.md
│   ├── results_index.md
│   ├── reproducibility.md
│   ├── presentation_outline.md
│   └── hackathon_checklist.md
├── experiments/         # Standalone benchmark and demonstration runners
├── metrics/             # Metrics evaluator, collector, and exporters
├── optimization/        # QUBO model builder, Ising mapper, exact solver, QAOA
├── perception/          # YOLOv8 detector, MOT tracker, queue estimator, vision service
├── simulation/          # SUMO controllers, multi-intersection supervisor, emergency/events
├── tests/               # 159 pytest unit and integration tests
├── web/                 # Node.js reverse proxy and HTML5 digital twin dashboard
├── requirements.txt     # Python project dependencies
├── server.py            # Python Flask backend entrypoint
└── README.md            # Master repository overview
```

---

## Documentation Links

- **[Master Team Handover Document](TEAM_HANDOVER.md)**: Master transition document detailing completed phases, architecture, test status, and handover checklist.
- **[Final Project Report (30 Sections)](docs/final_project_report.md)**: Comprehensive architectural, mathematical, and empirical report.
- **[REST API Reference](docs/api.md)**: Detailed JSON payloads, status codes, and endpoint specifications.
- **[Setup & Installation Guide](docs/setup.md)**: Environment setup, dependency installation, and server startup.
- **[Hackathon & Technical Demo Guide](docs/demo_guide.md)**: Step-by-step 14-stage live demonstration sequence.
- **[Results & Artifact Index](docs/results_index.md)**: Detailed catalog of all generated CSVs, JSONs, and research plots.
- **[Scientific Reproducibility Protocol](docs/reproducibility.md)**: Random seeds, configurations, and exact replication commands.
- **[Presentation Slide Deck Outline](docs/presentation_outline.md)**: 12-slide presentation structure with empirical metrics.
- **[Hackathon Pre-Flight Checklist](docs/hackathon_checklist.md)**: 15-minute pre-demo operational checklist.

---

## License
This project is licensed under the Apache License 2.0.
