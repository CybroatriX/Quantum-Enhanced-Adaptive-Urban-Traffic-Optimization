# FlowQ Environment Setup & Installation Guide

This guide details the complete procedure to install dependencies, verify prerequisites, launch local development servers, run regression tests, and execute research benchmarks.

---

## 1. Prerequisites & System Requirements

### Hardware Recommendations
- **CPU**: Multi-core processor (Intel Core i5/i7/i9, AMD Ryzen 5/7/9, or Apple Silicon).
- **RAM**: Minimum 8 GB (16 GB recommended for multi-seed SUMO and Qiskit circuit simulations).
- **Disk Space**: At least 4 GB free space for Python virtual environment, YOLO model weights, and SUMO network files.

### Required Software
| Software Component | Minimum Version | Verified Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Python** | 3.10+ | 3.14.4 / 3.11+ | Backend services, QUBO formulation, QAOA quantum circuits, YOLO perception |
| **Node.js** | 18.0+ | 22.14.0 | Dashboard frontend server, reverse proxy bridge, web test runner |
| **Eclipse SUMO** | 1.18+ | 1.27.1 | Microscopic traffic simulation and TraCI vehicle kinematics |
| **Git** | 2.30+ | Current | Version control |

---

## 2. Environment Setup & Dependency Installation

### Step 1: Clone Repository
```powershell
git clone https://github.com/CybroatriX/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization.git
cd Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1
```

### Step 2: Python Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### Step 3: Install Python Dependencies
```powershell
pip install -r requirements.txt
```

*Core Python Packages Installed:*
- `qiskit>=1.0.0` & `qiskit-aer>=0.14.0`: Quantum circuit construction, variational operators, and statevector simulation.
- `ultralytics>=8.0.0`: YOLOv8 object detection.
- `flask>=3.0.0`: REST API optimization backend.
- `traci>=1.18.0` & `sumolib>=1.18.0`: SUMO simulation control interface.
- `numpy`, `scipy`, `matplotlib`: Numerical operations, COBYLA optimizer, and research plotting.
- `pytest>=8.0.0`: Unit and integration testing.

### Step 4: Eclipse SUMO Configuration
Ensure SUMO is installed and added to your system environment:
```powershell
# Set SUMO_HOME environment variable (example for Windows)
$env:SUMO_HOME = "C:\Program Files (x86)\Eclipse\Sumo"
$env:PATH += ";$env:SUMO_HOME\bin"

# Verify SUMO installation
sumo --version
netconvert --version
```
*(Note: If SUMO is not installed, unit tests and mock simulations will run with clear fallback messages).*

### Step 5: Node.js Frontend Dependencies
```powershell
cd web
npm install
cd ..
```

---

## 3. Starting the System Services

FlowQ operates with a dual-service architecture: the Python Flask optimizer runs on port `5001`, and the Node.js web server/proxy runs on port `4173`.

### Terminal 1: Launch Python Optimization Backend
```powershell
python server.py
```
*Output confirmation:*
```text
* Running on http://127.0.0.1:5001
* Ready to accept QUBO and QAOA optimization requests
```

### Terminal 2: Launch Node.js Web Dashboard & Proxy
```powershell
node web/server.js
```
*Output confirmation:*
```text
FlowQ Quantum Mobility Command running at http://localhost:4173
Proxying /api/* to Python backend at http://127.0.0.1:5001
```

Once running, open your web browser to:
**`http://localhost:4173/`**

---

## 4. Running the Test Suites

### Full Python Regression Suite
```powershell
python -m pytest -q
```
*Expected Result:* **159 passed in ~35s**

### Node.js Integration & Bridge Test Suite
```powershell
cd web
npm test
cd ..
```
*Expected Result:* **9 passed in ~5s**

### Comprehensive Phase O End-to-End Test
```powershell
python -m pytest tests/test_end_to_end_validation.py -v
```
*Expected Result:* **10 passed in ~4s**

---

## 5. Running Standalone Demonstrations & Benchmarks

### 1. Classical vs Quantum Benchmark (Phase N)
Executes 60 SUMO simulations and 240 QAOA decisions across 5 random seeds, comparing Fixed-Time, Classical Adaptive, QUBO Exact, and QAOA:
```powershell
python experiments/run_classical_vs_quantum.py
```
*Generates:* `data/results/phase_n_comparison.csv`, `data/results/phase_n_summary.csv`, and 5 high-resolution research plots.

### 2. End-to-End System Validation (Phase O)
Executes a complete representative lifecycle (Normal state $\to$ QUBO Exact $\to$ QAOA $\to$ Accident at J2 $\to$ Ambulance Preemption $\to$ Corridor Release $\to$ Metrics):
```powershell
python experiments/run_end_to_end_validation.py
```
*Generates:* `data/results/phase_o_validation.json` and `data/results/phase_o_validation.csv`.

### 3. Emergency Green Corridor Demonstration
```powershell
python experiments/run_emergency_corridor_demo.py
```

### 4. Dynamic Traffic Events Demonstration
```powershell
python experiments/run_dynamic_events_demo.py
```

### 5. Multi-Intersection Coordination Demonstration
```powershell
python experiments/run_multi_intersection_demo.py
```

### 6. Real-World Vision Prototype Pipeline Demonstration
```powershell
python experiments/run_realworld_perception_demo.py
```
