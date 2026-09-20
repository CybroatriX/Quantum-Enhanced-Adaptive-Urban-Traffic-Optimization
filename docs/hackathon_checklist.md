# FlowQ Hackathon Demo & Live Judging Verification Checklist

Use this pre-flight verification checklist 15 minutes before presenting to hackathon judges, mentors, or faculty review panels.

---

## 1. Environment & Pre-Flight Checks

| Status | Verification Item | Command / Check | Expected Result |
| :---: | :--- | :--- | :--- |
| [ ] | **Python Environment** | `python --version` | Python 3.10+ (tested on 3.14.4 / 3.11+) |
| [ ] | **Python Dependencies** | `pip list` | `qiskit`, `qiskit-aer`, `ultralytics`, `flask`, `pytest` present |
| [ ] | **Node.js Environment** | `node --version` | Node.js v18.0+ (tested on v22.14.0) |
| [ ] | **SUMO Binaries** | `sumo --version` | Eclipse SUMO 1.18+ (tested on 1.27.1) |
| [ ] | **YOLOv8 Weights** | Test file presence: `Test-Path yolov8n.pt` | File exists (`yolov8n.pt`, ~6.2 MB) |
| [ ] | **Quantum Libraries** | `python -c "import qiskit, qiskit_aer; print('QAOA OK')"` | Prints `QAOA OK` |

---

## 2. Server Startup & Health Probes

| Status | Verification Item | Command / Action | Expected Result |
| :---: | :--- | :--- | :--- |
| [ ] | **Start Python Backend** | Terminal 1: `python server.py` | Runs on `http://127.0.0.1:5001` |
| [ ] | **Start Node Web Server** | Terminal 2: `node web/server.js` | Runs on `http://localhost:4173` |
| [ ] | **Python Health Endpoint** | Open browser to `http://127.0.0.1:5001/api/health` | `{"ok": true, "status": "ready"}` |
| [ ] | **Node Proxy Health** | Open browser to `http://localhost:4173/api/health` | `{"ok": true, "pythonBackend": "connected"}` |
| [ ] | **Dashboard Load** | Open browser to `http://localhost:4173/` | Dark glassmorphic interface renders |

---

## 3. Core Subsystem Operational Tests

| Status | Verification Item | Command / Test | Verification Criteria |
| :---: | :--- | :--- | :--- |
| [ ] | **Full Python Regression** | `python -m pytest -q` | **159 passed** in ~35s |
| [ ] | **Node.js Suite** | `cd web; npm test` | **9 passed** in ~5s |
| [ ] | **End-to-End Validation** | `python -m pytest tests/test_end_to_end_validation.py -v` | **10 passed** |
| [ ] | **Optimization API** | Click **Optimize Network** on dashboard | Junctions update with valid green timings |
| [ ] | **Emergency Corridor** | Dispatch route `J-01 -> J-04` on dashboard | Green corridor locks; priority status active |
| [ ] | **Dynamic Event** | Inject accident on `J-02 East` | Capacity drops to 35%; queue backs up |
| [ ] | **Metrics Evaluation** | Inspect **Metrics** tab on dashboard | Delay, throughput, fuel, $\text{CO}_2$ update live |
| [ ] | **QAOA Research Mode** | Toggle solver to QAOA on dashboard | 2-qubit Hamiltonian and probabilities display |
| [ ] | **Real-World Vision** | Switch to **Real-World Prototype** tab | Video stream renders with approach ROIs |

---

## 4. Backup Demo Paths (In Case of Venue Hardware / Network Issues)

1. **No External Internet Access**:
   - The entire FlowQ system runs 100% locally on `localhost`. No cloud API keys, external CDNs, or remote compute servers are required.
2. **SUMO Binary Not Configured on Presentation Laptop**:
   - The system automatically detects missing TraCI and seamlessly falls back to high-fidelity browser canvas simulations and pre-recorded SUMO benchmark logs.
3. **No GPU Available for YOLOv8**:
   - YOLOv8 runs in CPU inference mode (`yolov8n.pt` requires only ~28ms on standard modern laptop CPUs).
   - If OpenCV or PyTorch fails, the built-in synthetic mock detector activates automatically to guarantee presentation continuity.
4. **Python Backend Crash or Accidental Termination**:
   - The Node.js reverse proxy automatically falls back to an internal client-side JavaScript QUBO implementation (`optimizer.js`), ensuring that the dashboard remains interactive with offline status badges.
