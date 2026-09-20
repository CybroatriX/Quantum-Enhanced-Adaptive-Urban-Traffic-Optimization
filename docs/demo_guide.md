# FlowQ Hackathon & Technical Demonstration Guide

This guide provides a structured, step-by-step walkthrough for live hackathon presentations, faculty reviews, and technical project demonstrations.

---

## Demonstration Overview

| Step | Focus Area | Key Action | What Judges / Reviewers See |
| :---: | :--- | :--- | :--- |
| **1** | System Startup | Launch Python backend | `python server.py` runs Flask optimizer on port 5001 |
| **2** | Dashboard Startup | Launch Node.js proxy | `node web/server.js` serves web UI at `http://localhost:4173` |
| **3** | Digital Twin Grid | Inspect Network Canvas | 8 coordinated intersections (`COIMBATORE-08` topology) |
| **4** | Telemetry Ingestion | Inspect Junction Detail | Live directional queues, vehicle classification breakdown |
| **5** | Classical QUBO | Run Optimization | Discrete green candidates ($22\text{s}, 30\text{s}, 40\text{s}$) evaluated |
| **6** | Signal Execution | Safe Phase Transition | 4s fixed yellow, all-red clearance, safe phase-boundary shift |
| **7** | Dynamic Incident | Inject Accident at J2 | Road capacity drops to 35%, East approach queue backs up |
| **8** | Adaptive Recovery | Re-optimize Network | QUBO reallocates green time ($40\text{s}$) to clear incident queue |
| **9** | Emergency Dispatch | Request Corridor J1 $\to$ J4 | Emergency vehicle `AMB_001` requests arterial preemption |
| **10** | Green Wave Wavefront | Priority Preemption | Corridor locks priority green ($40\text{s}$ priority / $22\text{s}$ cross) |
| **11** | Clean Release | Progress Vehicle & Release | Traversed junctions release progressively back to QUBO |
| **12** | Sustainability Metrics | Inspect Metrics Panel | Real-time delay, throughput, fuel ($0.00025\text{ L/s}$), $\text{CO}_2$ emissions |
| **13** | Quantum Research Mode | Switch to QAOA Mode | Variational Ansatz, 2-qubit Ising Hamiltonian, $93.3\%$ recovery |
| **14** | Real-World Prototype | Inspect Vision Tab | Video/RTSP stream, approach ROIs, advisory recommendation |

---

## Detailed Step-by-Step Sequence

### Step 1: Start Python Backend
In Terminal 1:
```powershell
python server.py
```
*Talking Point*: "The Python backend provides the canonical mathematical optimizer. It runs the exact QUBO solver, the QAOA quantum circuit simulator, and manages the multi-intersection emergency/event supervisors."

### Step 2: Start Web Dashboard
In Terminal 2:
```powershell
node web/server.js
```
Open your browser to `http://localhost:4173/`.
*Talking Point*: "The Node.js server acts as an enterprise-grade reverse proxy. It serves our dark glassmorphic digital twin command interface and seamlessly forwards optimization requests to the Python backend."

### Step 3: Network Grid Overview
On the dashboard:
- Look at the top status bar: Verify badges display `LIVE DIGITAL TWIN`, `QUBO BACKEND ONLINE`, and `QAOA READY`.
- View the 2D interactive city canvas: Note 8 connected junctions (`J-01` through `J-08`) with simulated vehicle kinematics.
*Talking Point*: "We model an arterial network with dual-lane approaches, turning lanes, and real-time vehicle kinematics."

### Step 4: Live Traffic State & Perception Telemetry
Click on junction `J-01` on the grid or use the Junction Selector dropdown:
- Point out the **Queue Lengths**: North: 14, South: 12, East: 3, West: 3.
- Point out the **Vehicle Breakdown**: Cars ($75\%$), Motorcycles ($12\%$), Buses ($6\%$), Trucks ($7\%$).
- Show the **Detection Confidence**: $94.2\%$ mean YOLOv8 tracking confidence.
*Talking Point*: "Every intersection state conforms to our immutable `TrafficObservation` data contract, guaranteeing consistent schema whether data originates from SUMO, the browser digital twin, or YOLOv8 video tracking."

### Step 5: Run QUBO Optimization
Select **QUBO Exact** in the algorithm selector and click **Optimize Network**:
- The console and cards immediately display optimal timings:
  - `J-01`: Phase 0 (North-South) = **40s**, Phase 2 (East-West) = **22s**.
  - Objective Energy: $9.8587$.
*Talking Point*: "The QUBO formulation models delay reduction, queue balancing, and a $60\text{s}$ target cycle constraint, using a $50.0$ penalty to enforce strict single-phase selection."

### Step 6: Safe Phase Transition
Observe the traffic light transitions on the canvas:
- Signals do NOT snap abruptly; they transition through a mandatory **4-second yellow interval** and all-red clearance.
- Timing updates take effect strictly at safe phase boundaries.
*Talking Point*: "Safety is paramount. The system preserves phase clearance intervals and applies a $15\text{s}$ anti-oscillation damping to prevent erratic phase switching."

### Step 7: Dynamic Event Injection (Accident at J-02)
Navigate to the **Dynamic Events** tab:
- Select Event Type: `Accident`.
- Select Intersection: `J-02`, Approach: `East`. Severity: `High`.
- Click **Trigger Dynamic Event**.
- Observe the event badge appear on the canvas: East approach capacity drops from $100\%$ to $35\%$, and an incident queue forms.

### Step 8: Adaptive Event Recovery
Click **Optimize Network** or allow the automatic 30s cycle update to fire:
- Notice that the controller detects the congested East approach and reallocates green timing to Phase 2 (East-West = **40s**, North-South = **22s**).
- The East approach queue clears rapidly.
- Click **Resolve Event** to demonstrate clean expiration back to normal capacity.

### Step 9 & 10: Emergency Green Corridor Priority (Ambulance Route J1 $\to$ J4)
Navigate to the **Emergency Corridor** tab:
- Select Route: `J-01 -> J-02 -> J-03 -> J-04`.
- Priority Level: `CRITICAL`.
- Click **Dispatch Emergency Corridor**.
- **Visual WOW Factor**: The corridor lights up with green arrows on the canvas. Signals along the path lock into green wave priority ($40\text{s}$ priority approach / $22\text{s}$ competing cross-traffic).
*Talking Point*: "Our preemption engine resolves directional arrival approaches dynamically. Cross-traffic is held safely at minimum green while the ambulance encounters uninterrupted green waves."

### Step 11: Progressive Traversal & Clean Release
Click **Step / Advance Vehicle**:
- The ambulance advances from `J-01` to `J-02`. Notice that `J-01` status immediately switches to `Released` and resumes normal QUBO timing, while `J-02` through `J-04` remain prioritized.
- Advance to destination (`J-04`) and click **Release Corridor**. All intersections return cleanly to adaptive QUBO control.
*Talking Point*: "Measured arterial travel time was cut from $153.3\text{s}$ down to $60.0\text{s}$, saving over $93\text{s}$ without causing secondary gridlock."

### Step 12: Environmental Sustainability Metrics
Click on the **Metrics / Sustainability** tab:
- Review live network metrics: Throughput ($1,680\text{ veh/h}$), Total Waiting Time ($240\text{s}$), Fuel Consumption ($45.67\text{ L}$), and $\text{CO}_2$ Emissions ($105.50\text{ kg}$).
*Talking Point*: "We evaluate emissions using calibrated stoichiometric models: $0.00025\text{ L/s}$ idle fuel consumption and $2,392\text{ g CO}_2/\text{L}$, enabling municipalities to quantify real environmental benefits."

### Step 13: Quantum QAOA Research Mode
Click on the **QAOA Research** tab and toggle solver to **QAOA**:
- Inspect the 2-qubit Ising Hamiltonian formulation:
  $$H_C = 0.5 Z_0 Z_1 - 1.2 Z_0 + 0.8 Z_1 + 2.4 I$$
- View the quantum state probability histogram and measured ground-state recovery.
*Talking Point*: "In Phase N benchmarks across 240 decisions, QAOA at depth $p=1$ achieved a $93.33\%$ recovery of the exact classical optimum with zero infeasible solutions. We provide this as a rigorous research pathway for next-generation quantum hardware."

### Step 14: Real-World Vision Prototype Interface
Click on the **Real-World Prototype** tab:
- View the live camera / sample video stream (`VIRTUAL-01`).
- Show the 4 polygonal Approach ROIs (North, South, East, West) overlaid on the video frame.
- Point out the velocity-based queue estimation ($v < 0.5\text{ m/s}$ stopped queue threshold).
- Review the generated advisory signal recommendation card.
*Talking Point*: "This proves the end-to-end viability of the technology: taking raw pixel frames, passing them through YOLOv8 and tracking, deriving directional queues, and computing optimal signal plans—all while clearly labeling outputs as advisory research prototypes."

---

## Demo Summary & Conclusion
Conclude the demonstration with:
> "FlowQ demonstrates a complete, closed-loop urban mobility intelligence system. From micro-perception video tracking to exact QUBO optimization, emergency corridors, dynamic event resilience, and quantum QAOA research, the platform bridges today's municipal traffic challenges with tomorrow's quantum computing capabilities."
