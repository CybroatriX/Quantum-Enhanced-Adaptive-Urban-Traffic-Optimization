# QUANTUM-ENHANCED ADAPTIVE URBAN TRAFFIC OPTIMIZATION

## TEAM HANDOVER

## PROJECT STATUS

### Phase 1 — SUMO Traffic Foundation: COMPLETE

- SUMO 1.27.1
- 4 connected intersections
- TraCI integration
- Fixed-time signal controller
- Low / Normal / High traffic scenarios
- Waiting time, queue length and throughput metrics
- Tests verified

### Phase 2 — Classical Adaptive Signals: COMPLETE

- Fixed controller preserved
- Rule-based adaptive controller
- Queue/density-based adaptation
- Configurable green-time constraints
- Same seed/duration comparison
- 15 tests passed during Phase 2 validation

### Phase 3A — QUBO / Exact Classical Validation: COMPLETE

- QUBO formulation
- 9 binary variables
- One-hot timing selection
- Queue/waiting objective
- Demand imbalance objective
- Timing/cycle regularization
- Constraint penalties
- Exact classical enumeration
- `phase3a_qubo_validation.csv`

### Phase 3B — QAOA / Aer: COMPLETE

- QUBO -> Ising conversion
- QAOA circuit
- Qiskit Aer execution
- p=2
- COBYLA optimizer
- 2048 shots
- Seeded sampling
- Original-QUBO scoring
- Exact-vs-QAOA validation
- Multi-seed sensitivity experiment
- `phase3b_qaoa_validation.csv`
- `phase3b_qaoa_sensitivity.csv`
- `phase3b_qaoa_sensitivity_summary.csv`

## LATEST VALIDATION

29 tests passed

QAOA sensitivity:

- 15 seed/state observations
- Exact-optimum recovery rate: 0.600
- Average objective gap: 1.317048836050996
- Balanced recovery rate: 0.600
- Phase-0-heavy recovery rate: 0.600
- Phase-2-heavy recovery rate: 0.600

## IMPORTANT

Do not fabricate or alter QAOA results.

The current work covers the formal mathematical formulation and algorithm
implementation. Remaining system integration such as computer vision,
emergency green corridor, DeepStream and dashboard can be handled by the rest
of the team.

## SETUP

1. Install SUMO 1.27.1.
2. Create/activate a Python virtual environment.
3. Run `python -m pip install -r requirements.txt`.
4. Run tests: `python -m pytest -q`.

Useful QAOA command:

```powershell
python -m experiments.run_qaoa_demo
```

Sensitivity experiment:

```powershell
python -m experiments.run_qaoa_sensitivity
```
