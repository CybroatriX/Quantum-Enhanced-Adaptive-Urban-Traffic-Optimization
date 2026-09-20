# FlowQ: Project Presentation Slide Deck Outline
*A 12-Slide Technical & Scientific Presentation for Hackathon Judging and Academic Review.*

---

## Slide 1: Title & Executive Summary
- **Title**: FlowQ: Quantum-Enhanced Adaptive Urban Traffic Optimization
- **Subtitle**: A Hybrid Classical-Quantum Digital Twin and Micro-Perception Pipeline for Resilient Urban Mobility Grid Control
- **Presenters**: The CybroatriX / FlowQ Research Team
- **Core Message**: Uniting computer vision perception, microscopic simulation, and quantum mathematical optimization into a unified, fail-safe urban traffic management system.

---

## Slide 2: The Urban Gridlock Problem
- **Urban Congestion**: Global cities lose hundreds of billions annually to traffic gridlock.
- **Environmental Impact**: Stop-and-go vehicle idling accounts for massive localized greenhouse gas emissions and particulate pollution.
- **Emergency Delays**: Ambulances and fire engines lose critical golden-hour minutes navigating uncoordinated red-light queues.
- **Static Infrastructure**: Traditional fixed-time controllers rely on static historical tables that cannot react to dynamic surges or accidents.

---

## Slide 3: Motivation & The Quantum Optimization Frontier
- **Combinatorial Explosion**: Optimizing phase timings across multi-intersection networks is an NP-hard combinatorial problem that scales exponentially with grid size.
- **Why Quantum?**: Quadratic Unconstrained Binary Optimization (QUBO) maps naturally to Ising spin systems, allowing quantum variational heuristics (QAOA) to explore complex solution spaces.
- **The Gap**: Bridging theoretical quantum computing with real-world sensor streams and municipal traffic safety constraints.

---

## Slide 4: End-to-End System Architecture
- **Perception Layer**: YOLOv8 vehicle detection $\to$ MOT centroid tracking $\to$ ray-casting ROI queue estimation.
- **Canonical Schema**: Single immutable `TrafficObservation` JSON contract shared across all modules.
- **Optimization Layer**: Independent per-junction 9-variable QUBO formulation $\to$ exact classical baseline and QAOA research path.
- **Supervisory Control**: Deterministic preemption hierarchy:
  $$\text{Safety Clearance} \succ \text{Emergency Priority Corridor} \succ \text{Dynamic Event Adaptation} \succ \text{Normal QUBO / QAOA}$$
- **Execution & Telemetry**: Phase-boundary timing injection, stoichiometric emissions modeling, and dark glassmorphic dashboard.

---

## Slide 5: Computer Vision Micro-Perception & Queue Estimation
- **Detector**: Ultralytics YOLOv8n detecting `car`, `bus`, `truck`, `motorcycle` with mean confidence $> 94\%$.
- **Spatial ROI Assignment**: Ray-casting point-in-polygon algorithm classifies vehicle centroids into North, South, East, and West approach polygons.
- **Velocity-Based Queue Filter**:
  - Moving vehicles: $v \ge 2.5\text{ m/s}$ ($9.0\text{ km/h}$)
  - Stopped queue: $v < 0.5\text{ m/s}$ ($1.8\text{ km/h}$)
- **Fail-Safe Operation**: Built-in synthetic fallback detector guarantees continuous pipeline operation even without local GPU weights.

---

## Slide 6: Adaptive Signal Control & Safety Invariants
- **Dynamic Phase Adaptation**: Reallocates green timing from discrete candidate durations ($22\text{s}, 30\text{s}, 40\text{s}$) to balance directional queues.
- **Non-Negotiable Safety Invariants**:
  - Strictly no conflicting green lights.
  - Mandatory 4-second fixed yellow interval preserved across all transitions.
  - All-red clearance intervals maintained.
  - Positive green bounds strictly clamped within $[22\text{s}, 42\text{s}]$.
  - $15\text{s}$ anti-oscillation damping prevents erratic hunting under sensor noise.

---

## Slide 7: QUBO Mathematical Formulation
- **Decision Space**: 9 binary variables $x_{i,j} \in \{0, 1\}$ representing pairs of green durations $(g_0, g_2) \in \{22\text{s}, 30\text{s}, 40\text{s}\}^2$.
- **Cost Function**:
  $$\min_{\mathbf{x}} E(\mathbf{x}) = \mathbf{x}^T \mathbf{Q} \mathbf{x}$$
  - $w_{\text{wait}} \cdot \text{Delay}(g_0, g_2)$ (minimizes waiting queues).
  - $w_{\text{imb}} \cdot \text{Imbalance}(g_0, g_2)$ (balances directional approach queues).
  - $w_{\text{cyc}} \cdot (g_0 + g_2 - 60)^2$ (damps cycle duration drift).
  - Quadratic penalty $P = 50.0 \cdot (\sum x_k - 1)^2$ enforces strict single-choice selection.
- **Exact Classical Solver**: Direct exhaustive search across all 9 states delivers the mathematically provable global optimum in $0.85\text{ ms}$.

---

## Slide 8: Quantum QAOA Research Component
- **Ising Mapping**: Algebraic transformation $x_k = (I - Z_k)/2$ generates the cost Hamiltonian:
  $$H_C = \sum_{k < l} J_{kl} Z_k Z_l + \sum_k h_k Z_k + \text{offset} \cdot I$$
- **Variational Ansatz**: Depth $p=1$ quantum circuit parameterized by $(\gamma, \beta)$ optimized via classical COBYLA.
- **Simulation**: Qiskit Aer statevector simulation with 1024 measurement shots.
- **Empirical Findings (240 Decisions)**:
  - **$93.33\%$ Overall Exact-Optimum Recovery Rate** ($100\%$ in Low traffic, $92.5\%$ in Normal, $87.5\%$ in High).
  - **$100\%$ Feasible Solutions** (zero invalid or non-one-hot bitstrings selected).

---

## 9. Slide 9: Emergency Corridor & Dynamic Resilience
- **Emergency Priority Preemption**:
  - Route preemption across connected junctions (e.g., `J1 -> J2 -> J3 -> J4`).
  - Arrival approach automatically mapped to green wave ($40\text{s}$ priority green / $22\text{s}$ cross).
  - Progressive release: Junctions release back to QUBO immediately after vehicle traversal.
  - **Measured Travel Time**: Dropped from $153.3\text{s}$ down to $60.0\text{s}$ (**$93.3\text{s}$ saved**).
- **Dynamic Events**:
  - Ingests accidents (capacity drop to 35%), road closures (capacity drop to 5%), and surges.
  - Re-optimizes effective traffic states without mutating base QUBO algorithms.

---

## Slide 10: The FlowQ Mobility Command Dashboard
- **Interactive Digital Twin**: High-performance HTML5 canvas simulating 8 coordinated intersections (`COIMBATORE-08` topology).
- **Real-Time Telemetry**: Live phase indicators, approach queue lengths, and vehicle classifications.
- **Integrated Panels**:
  - Network Grid Overview
  - Junction Inspector
  - Emergency Dispatcher & Progressive Step Controls
  - Dynamic Incident Injection
  - Sustainability Telemetry (Throughput, Delay, Fuel, $\text{CO}_2$)
  - Quantum QAOA Inspector
  - Real-World Video / Camera Prototype Stream

---

## Slide 11: Experimental Benchmark Evaluation
- **Benchmark Scale**: 60 SUMO simulations across 4 controllers, 3 demand profiles, and 5 random seeds.
- **Full Regression**: **159 / 159 Python tests passed**; **9 / 9 Node tests passed**.
- **Environmental Modeling**:
  - Calibrated fuel consumption: $0.00025\text{ L/s}$ idle, $0.00070\text{ L/s}$ cruise.
  - Stoichiometric emissions: $2,392\text{ g CO}_2 / \text{L}$.
- **Performance Profiling**:
  - Exact QUBO: $0.85\text{ ms}$ / junction ($3.33\text{ ms}$ for 4-junction batch).
  - QAOA Simulation: $625.9\text{ ms}$ / junction.
  - Bit-for-bit classical deterministic reproducibility verified ($\Delta = 0.000000$).

---

## Slide 12: Limitations, Future Work & Conclusion
- **Honest Engineering Limitations**:
  - Simulated vehicle kinematics (SUMO) rather than physical street loops.
  - QAOA evaluated via classical statevector simulation, not noisy physical QPUs.
  - Camera queue estimation is pixel-displacement based (requires extrinsic camera calibration).
  - Real-world vision interface produces advisory recommendations, not physical light actuation.
- **Future Roadmap**:
  - Physical QPU execution on IBM Quantum / IonQ hardware.
  - Hardware-in-the-loop (HIL) traffic cabinet integration via NTCIP 1202.
  - Multi-agent coupled network QUBO formulations.
- **Conclusion**: FlowQ establishes a complete, safe, and reproducible blueprint for the future of quantum-enhanced intelligent transportation systems.
