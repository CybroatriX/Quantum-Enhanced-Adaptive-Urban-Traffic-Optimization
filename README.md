# Quantum-Enhanced Adaptive Urban Traffic Optimization

Phases 1–2 provide a SUMO foundation and a **classical rule-based adaptive controller**. Phase 3A now adds a small QUBO formulation plus exact classical validation for one intersection. The project still does **not** implement QAOA, real quantum hardware, computer vision, emergency corridors, emissions, or a dashboard.

## Included

- Four signalized intersections (J1-J4) arranged as a connected 2-by-2 road network.
- Two lanes in every direction and synthetic multi-route vehicle demand.
- YAML-configured low, normal, and high demand profiles.
- YAML-configured fixed-time and classical adaptive traffic-light control.
- Python APIs for SUMO lifecycle, intersection state, and measured waiting/queue/throughput metrics.
- A nine-variable, one-hot Phase-3A signal-timing QUBO with exact exhaustive validation.
- Tests for the data contract, demand, metrics, and live SUMO behavior when available.

## Prerequisites

Install [Eclipse SUMO](https://sumo.dlr.de/docs/Downloads.html), including `sumo` and `netconvert`. Add SUMO's `bin` folder to `PATH`, or set `SUMO_HOME` to the installation directory. Python 3.11 or 3.12 is recommended for the current SUMO Python packages.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

Build the generated SUMO network once:

```powershell
python -m simulation.network.build_network
```

Run a fixed-time scenario (the runner also builds a missing network and generates routes):

```powershell
python -m simulation.run --scenario normal
python -m simulation.run --scenario low
python -m simulation.run --scenario high --duration 300
```

Run the Phase-2 classical adaptive controller:

```powershell
python -m simulation.run --scenario normal --controller adaptive
```

Run the fair six-experiment comparison. Each fixed/adaptive pair receives the same scenario, duration, network, and random seed. The command writes measured results to `data/results/classical_comparison.csv`.

```powershell
python -m experiments.run_comparison --duration 900
```

Run the Phase-3A QUBO demonstration and its exact classical validation:

```powershell
python -m experiments.run_qubo_demo
```

The output is measured from the simulation: completed-vehicle average waiting time, average observed queue length, and completed-vehicle throughput. It contains no embedded performance claims.

## Test

```powershell
pytest
```

Live SUMO checks skip with a clear reason if SUMO, `netconvert`, or TraCI is missing. Unit tests remain runnable after `pip install -r requirements.txt`.

## Controllers

`fixed` remains the Phase-1 baseline: every green and yellow phase uses the configured fixed duration.

`adaptive` is Phase 2's **classical rule-based controller**, not quantum optimization. Every configured re-evaluation interval it reads queue/density data and prepares a duration for each green phase. The fixed 30-second green is retained whenever directional queues are balanced. Only an imbalance meeting the configured threshold changes timing: the highest-demand movement is extended, the lowest-demand movement is shortened, and high density can add a small additional extension. A minimum interval between adjustments prevents repeated changes. The controller preserves SUMO's existing green-to-yellow sequence and only sets green duration at a phase boundary.

Adaptive settings live in [config/simulation.yaml](config/simulation.yaml): minimum/maximum green, yellow, cycle bounds, low-traffic threshold, re-evaluation interval, and rule weights. Initial Phase-2 adaptation is independent per intersection; network coordination is intentionally deferred.

Phase 3A is an offline formulation and validation boundary; it does not control a running SUMO signal. It uses the same `IntersectionTrafficState` data contract, including green-phase queues emitted by `TrafficStateReader`. See [the QUBO formulation](optimization/quantum/README.md) for variables, penalties, matrix convention, and exact solver method.

## Fair-comparison methodology

`experiments.run_comparison` runs Low, Normal, and High demand for both controllers. Within every pair it uses exactly the same generated network, demand rate, simulation duration, and random seed. The CSV reports actual completed-vehicle waiting time, total waiting time, observed queue length, and throughput. It does not calculate or claim improvement percentages.

## Layout

```
simulation/       network source, demand, fixed/adaptive signals, runner, state reader
perception/       future vision integration boundary
optimization/     Phase-3A QUBO/exact validation and future quantum boundary
emergency/        future green-corridor boundary
metrics/          Phase-1 metric collector
experiments/      reproducible fixed-versus-adaptive comparison export
dashboard/        future UI boundary
config/           runtime configuration
data/sumo/        generated network/routes and SUMO config
tests/            unit and live-SUMO tests
```

## Current limits

Demand is synthetic, and the compact road network is not a calibrated city model. Adaptive signals are classical and independent per intersection. Fuel and CO2 result fields are present as `None` extension points; they are not calculated.
