# FlowQ Scientific Reproducibility & Benchmark Protocol

This document establishes the experimental methodology, software configurations, random seeds, and exact commands necessary to replicate all benchmark results presented in this project.

---

## 1. Experimental Conditions & Parameter Specifications

### Random Seeds
To eliminate stochastic bias, all multi-run benchmarks employ an identical set of 5 deterministic pseudorandom seeds:
$$\text{Seeds} = [42, 101, 202, 303, 404]$$

Within each seed run, all competing controllers (Fixed-Time, Classical Adaptive, QUBO Exact, QAOA) receive identical vehicle departure schedules, identical route assignments, and identical network geometry.

### Network Topology
- **Topology**: 4-intersection ($2 \times 2$) arterial grid network (`J1`, `J2`, `J3`, `J4`).
- **Road Geometry**: Dual-lane approach segments ($100\text{ m}$ length) with orthogonal cross-traffic lanes and standard $3.2\text{ m}$ lane widths.
- **Signal Logic**: Orthogonal two-phase cycle:
  - Phase 0: North-South green + East-West red.
  - Phase 1: North-South yellow ($4\text{s}$) + East-West red.
  - Phase 2: East-West green + North-South red.
  - Phase 3: East-West yellow ($4\text{s}$) + North-South red.

### Traffic Demand Scenarios
- **Low Traffic**: $360\text{ veh/h}$ total network entry rate ($90\text{ veh/h}$ per boundary entry edge).
- **Normal Traffic**: $720\text{ veh/h}$ total network entry rate ($180\text{ veh/h}$ per boundary entry edge).
- **High Traffic**: $1200\text{ veh/h}$ total network entry rate ($300\text{ veh/h}$ per boundary entry edge).
- **Simulation Duration**: $60.0\text{ seconds}$ per benchmark run (yielding 240 distinct signal phase optimization decisions across all intersections).

---

## 2. Controller & Optimizer Configurations

### A. Fixed-Time Controller
- Phase 0 Green: $30\text{ seconds}$
- Phase 2 Green: $30\text{ seconds}$
- Yellow Intervals: $4\text{ seconds}$ fixed
- Cycle Length: $68\text{ seconds}$

### B. Classical Adaptive Controller
- Baseline Green: $30\text{ seconds}$
- Min Green: $22\text{ seconds}$, Max Green: $42\text{ seconds}$
- Imbalance Threshold: $|q_{\text{NS}} - q_{\text{EW}}| \ge 6\text{ vehicles}$
- Damping Interval: Minimum $15\text{ seconds}$ between phase duration alterations
- Adaptation Logic: Rule-based heuristic extending congested phase up to $+12\text{s}$ and reducing competing phase by $-8\text{s}$.

### C. QUBO Exact Solver
- Candidate Green Durations: $\mathcal{G} = \{22\text{s}, 30\text{s}, 40\text{s}\}$
- Target Cycle Length: $T_{\text{target}} = 60\text{ seconds}$ (excluding yellow)
- Objective Weights:
  - $w_{\text{wait}} = 1.0$ (waiting time penalty)
  - $w_{\text{imb}} = 4.0$ (directional queue balance penalty)
  - $w_{\text{cyc}} = 20.0$ (cycle duration deviation penalty)
- One-Hot Selection Constraint Penalty: $P = 50.0$
- Solver Method: Exact exhaustive classical state-space search across all $3^2 = 9$ valid candidate configurations.

### D. Quantum Approximate Optimization Algorithm (QAOA)
- Hamiltonian Mapping: Algebraic substitution $x_i = (I - Z_i)/2$ into QUBO matrix $\mathbf{Q}$.
- Variational Circuit Depth: $p = 1$.
- Mixer Hamiltonian: Transverse field $H_M = \sum_{i=1}^9 X_i$.
- Parameter Optimizer: Classical **COBYLA** algorithm:
  - Initial parameters: $\boldsymbol{\gamma}_0 = [0.5]$, $\boldsymbol{\beta}_0 = [0.5]$
  - Max iterations: $100$
  - Convergence tolerance: $10^{-4}$
- Quantum Backend: Qiskit `AerSimulator` (statevector mode).
- Measurement Shots: $1024$ / $2048$.
- Seed Policy: Simulator seed fixed to master run seed to guarantee repeatable bitstring sampling.

---

## 3. Software Environment & Dependencies

| Dependency | Version Recorded |
| :--- | :--- |
| Operating System | Windows 11 (build 26100) / Linux compatible |
| Python Runtime | 3.14.4 / 3.11+ |
| Node.js Runtime | 22.14.0 |
| Eclipse SUMO | 1.27.1 |
| Qiskit | 2.5.2 |
| Qiskit Aer | 0.17.2 |
| Ultralytics YOLO | 8.3.89 (`yolov8n.pt`) |
| OpenCV (cv2) | 5.0.0 |
| Flask | 3.0.3 |
| NumPy | 2.2.3 |
| SciPy | 1.15.2 |
| Pytest | 8.3.5 |

---

## 4. Replication Execution Commands

### Step 1: Execute Classical vs Quantum Benchmark (Phase N)
```powershell
python experiments/run_classical_vs_quantum.py
```
*Expected Outcomes*:
- Runs 60 micro-simulations and 240 QAOA optimizations.
- Produces identical records in `data/results/phase_n_comparison.csv`.
- Confirms **$93.33\%$** exact-optimum recovery rate for QAOA.

### Step 2: Execute End-to-End System Validation (Phase O)
```powershell
python experiments/run_end_to_end_validation.py
```
*Expected Outcomes*:
- Validates full lifecycle: Normal $\to$ QUBO Exact $\to$ QAOA $\to$ Accident $\to$ Ambulance Preemption $\to$ Corridor Release $\to$ Metrics.
- Verifies bit-for-bit classical deterministic reproducibility ($\Delta = 0.000000$).
- Produces fresh validation logs in `data/results/phase_o_validation.json` and `.csv`.

### Step 3: Run Full Automated Regression Test Suites
```powershell
# Python unit and integration regression
python -m pytest -q

# Node.js frontend and proxy bridge regression
cd web
npm test
cd ..
```
*Expected Outcomes*: **159 / 159 Python tests pass**; **9 / 9 Node tests pass**.
