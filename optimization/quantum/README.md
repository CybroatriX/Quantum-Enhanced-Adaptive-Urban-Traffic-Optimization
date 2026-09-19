# Phase 3A: QUBO formulation and classical ground truth

Phase 3A selects timing for **one** SUMO intersection state. It does not alter signal order, invoke QAOA, use Qiskit, or claim a traffic improvement. The exact classical result is the ground truth for Phase 3B.

## Input contract

`IntersectionTrafficState` remains the traffic-state interface: vehicle count `v`, total queue `q`, density `rho`, capacity `C`, and current SUMO phase. It now exposes `green_phase_queues`, populated by the existing `TrafficStateReader` from SUMO controlled lanes. This avoids guessing a directional demand split from an aggregate queue.

The current network has two green phases: phase 0 and phase 2 (the generated grid's north/south and east/west movements). Phase numbers keep the model tied to SUMO's actual signal program.

## Binary variables

Candidate green values are `22`, `30`, and `40` seconds. For every pair `(a, b)`, one binary variable `x[a,b]` is one exactly when phase 0 gets `a` seconds and phase 2 gets `b` seconds. The nine ordered variables are:

`x_p0_22_p2_22`, `x_p0_22_p2_30`, `x_p0_22_p2_40`,
`x_p0_30_p2_22`, `x_p0_30_p2_30`, `x_p0_30_p2_40`,
`x_p0_40_p2_22`, `x_p0_40_p2_30`, `x_p0_40_p2_40`.

Exactly one variable must be one.

## Candidate objective

For phase queues `q0` and `q2`, any unassigned aggregate queue is split only to preserve the existing state contract. Let the resulting demands be `d0`, `d2`; let `D = d0 + d2`; and let `kappa = 1 + rho + v / max(C, 1)`.

For candidate times `g0`, `g2`, the base cost is `L(g0,g2) = W + I + R`:

`W = waiting_weight * kappa * [d0(1 - g0/gmax)^2 + d2(1 - g2/gmax)^2]`

`I = imbalance_weight * D * [g0/(g0+g2) - d0/D]^2`

`R = cycle_weight * [(g0+g2-target_total)/target_total]^2`

`W` is a bounded residual-queue/wait proxy. `I` penalizes a green-time share that differs from the observed demand share. `R` discourages unnecessary cycle growth, so the model does not automatically choose 40/40. Settings are in `config/simulation.yaml`.

## Constraint penalties and QUBO matrix

Valid candidates satisfy the current controller limits:

- `22 <= g0, g2 <= 42`
- `52 <= g0 + g2 + 2 * yellow_seconds <= 92`

The upper-triangular convention is:

`E(x) = offset + sum_i Qii*x_i + sum_(i<j) Qij*x_i*x_j`.

With one-hot penalty `P` and invalid-timing penalty `Pinvalid`:

`E(x) = sum_i L_i*x_i + P(sum_i x_i - 1)^2 + Pinvalid*sum_i invalid_i*x_i`.

Thus `offset = P`, `Qii = L_i - P + Pinvalid*invalid_i`, and `Qij = 2P` for every `i < j`. Both penalties are raised above the largest candidate base cost at build time, so invalid, zero-hot, and multi-hot assignments cannot beat a valid one-hot plan. No post-processing changes the optimizer selection.

The generated CSV stores the complete numerical QUBO matrix and variable mapping for each state. For the balanced demo, its diagonal is `[-995.063039, -996.970398, -997.191388, -996.970398, -998.734694, -998.549320, -997.191388, -998.549320, -997.742630]`; all upper off-diagonal entries are `2000.0`, the lower triangle is zero, and offset is `1000.0`.

## Classical validation

```powershell
python -m experiments.run_qubo_demo
```

The exact solver enumerates all `2^9 = 512` binary assignments, retains only valid one-hot plans, and writes selected timing, objective terms, mapping, and matrix to `data/results/phase3a_qubo_validation.csv`.

Phase 3B may replace only exhaustive search with QAOA/Aer and must compare its selected bitstring and objective to this exact ground truth.

## Phase 3B: QAOA / Qiskit Aer validation

Phase 3B keeps the Phase-3A QUBO, its penalties, variable order, and timing decoder unchanged. The exhaustive classical solver remains the ground truth for this nine-variable problem. QAOA is an experimental validation method; it is not assumed to outperform exact enumeration.

### Qubit mapping and cost Hamiltonian

Qubit `i` represents the same binary variable `x_i` in the Phase-3A variable list. The implementation converts the existing upper-triangular QUBO using `x_i = (1 - Z_i) / 2`. For QUBO energy `E(x)`, this produces a diagonal Ising cost `C + sum_i h_i Z_i + sum_(i<j) J_ij Z_i Z_j`. The scalar `C` is a global phase in the QAOA circuit, while every sampled bitstring is scored again with the original `QuboModel.energy` method.

### Circuit and Aer workflow

The circuit starts in `|+>^9`, then applies configurable alternating cost and mixer layers. Cost terms use `RZ(2*gamma*h_i)` and `RZZ(2*gamma*J_ij)`; mixer terms use `RX(2*beta)` on every qubit. Qiskit Aer `AerSimulator(method='statevector')` supplies deterministic objective estimates to COBYLA, then seeded Aer shot sampling supplies bitstrings. Qiskit count keys are reversed when decoded so qubit 0 remains Phase-3A variable 0.

Default reproducibility settings in `config/simulation.yaml`: two repetitions, 2,048 shots, random seed 42, COBYLA, and 100 optimizer iterations. They are experiment settings, not a claim of optimal QAOA tuning.

### Exact-versus-QAOA validation

Run `python -m experiments.run_qaoa_demo`. For each balanced, phase-0-heavy, and phase-2-heavy state, it builds the existing QUBO, enumerates its exact optimum, runs QAOA/Aer, discards invalid sampled one-hot assignments, and compares the best remaining sample's original-QUBO objective to the exact objective. The CSV records timing, objectives, objective gap, optional approximation ratio, parameters, seed, shots, simulator, and raw sample counts.

### Limitations

This is a nine-qubit simulator experiment, not real-hardware execution or evidence of a traffic-performance improvement. Outcomes depend on the fixed QUBO formulation, selected depth, optimizer, seed, and shot count. Constraint penalties can also make this small QUBO challenging for shallow QAOA. Phase 4 should first calibrate and test QAOA parameters against this exact ground truth before integrating quantum decisions into an online controller; it should not introduce multi-intersection optimization yet.

### Seed-sensitivity experiment

`python -m experiments.run_qaoa_sensitivity` holds the Phase-3A QUBO, QAOA depth (2), 2,048 shots, COBYLA, and 100 iterations fixed. It varies only the configured seeds `42, 43, 44, 45, 46` for each of the three validation states.

It writes one row per seed/state to `data/results/phase3b_qaoa_sensitivity.csv`, containing the exact objective, sampled QAOA objective, match flag, objective gap, timing, seed, shots, and repetitions. `data/results/phase3b_qaoa_sensitivity_summary.csv` records the overall exact-optimum recovery rate, average objective gap, and recovery rate for each state. A seed-dependent exact match is documented as stochastic sampling/optimization behavior; it is not a QUBO or objective change.
