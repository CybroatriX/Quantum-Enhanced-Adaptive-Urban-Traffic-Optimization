# FlowQ Experimental Results & Artifact Index

This index catalogs all empirical benchmark datasets, mathematical validation outputs, research plots, and integration reports generated across Phases 1 through Phase O.

---

## 1. Master Results Directory (`data/results/`)

### Phase N: Classical vs Quantum Empirical Benchmark
- **[`data/results/phase_n_comparison.csv`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_n_comparison.csv)**:
  - **Contents**: 60 individual SUMO micro-simulation benchmark runs across 4 controllers (Fixed-Time, Classical Adaptive, QUBO Exact, QAOA), 3 traffic scenarios (Low, Normal, High), and 5 reproducible random seeds (42, 101, 202, 303, 404).
  - **Metrics Included**: Average waiting time ($\text{s}$), total waiting time ($\text{s}$), average queue length ($\text{veh}$), throughput ($\text{veh/h}$), total fuel consumption ($\text{L}$), total $\text{CO}_2$ emissions ($\text{g}$), baseline deltas vs Fixed-Time, and solver execution runtimes ($\text{s}$).
- **[`data/results/phase_n_summary.csv`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_n_summary.csv)**:
  - **Contents**: Descriptive aggregate statistics (mean, median, standard deviation, min, max) for every scenario/controller pair, plus mean delta improvements over baseline fixed-time control.
- **[`data/results/phase_n_qaoa_analysis.csv`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_n_qaoa_analysis.csv)**:
  - **Contents**: Granular decision log of all 240 QAOA optimization decisions executed across the benchmark.
  - **Metrics Included**: Exact classical minimum objective energy, QAOA sampled objective energy, absolute objective gap $|E_{\text{QAOA}} - E_{\text{exact}}|$, binary ground-truth recovery flag (`recovered_optimum`), circuit depth $p=1$, measurement shots ($1024$), and quantum execution time.
- **[`data/results/phase_n_comparison.json`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_n_comparison.json)**:
  - **Contents**: Complete structured JSON export with full per-junction records, scenario configurations, and dedicated incident evaluation records (emergency preemption and dynamic accident disruption).
- **[`data/results/phase_n_experiment_config.json`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_n_experiment_config.json)**:
  - **Contents**: Machine-readable metadata detailing random seeds, network parameters, green duration bounds ($[22\text{s}, 42\text{s}]$), solver weights, and software runtime versions.

---

### Phase K: Sustainability & Metrics Layer Evaluation
- **[`data/results/phase_k_metrics.csv`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_k_metrics.csv)**:
  - **Contents**: Multi-scenario evaluation comparing Fixed-Time, Classical Adaptive, QUBO Exact, and QAOA under Low, Normal, High, Emergency, and Accident conditions.
- **[`data/results/phase_k_summary.csv`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_k_summary.csv)**:
  - **Contents**: High-level controller performance summary highlighting fuel savings and emissions deltas.
- **[`data/results/phase_k_metrics.json`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_k_metrics.json)**:
  - **Contents**: Per-intersection directional delay, queue distributions, and emergency corridor travel-time telemetry.

---

### Phase O: End-to-End System Validation & Profiling
- **[`data/results/phase_o_validation.json`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_o_validation.json)**:
  - **Contents**: Comprehensive JSON validation log containing full results for 16 deterministic scenarios (A–P), 14 failure handling tests, cross-boundary contract invariant checks, and classical deterministic reproducibility diffs.
- **[`data/results/phase_o_validation.csv`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_o_validation.csv)**:
  - **Contents**: Machine-readable validation status table listing every tested component, scenario ID, measured execution runtime, and pass/fail outcome.
- **[`docs/phase_o_validation_report.md`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/docs/phase_o_validation_report.md)**:
  - **Contents**: Full engineering and scientific validation report covering architecture verification, safety invariants, failure matrices, latency benchmarks, reproducibility, dashboard, and research limitations.

---

### Phase 2: Classical Fixed vs Adaptive Comparison
- **[`data/results/classical_comparison.csv`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/classical_comparison.csv)**:
  - **Contents**: Baseline 6-experiment SUMO comparison between Fixed-Time ($30\text{s}/30\text{s}$) and rule-based Classical Adaptive control across Low, Normal, and High demand profiles.

---

## 2. Visual Research Plots (`data/results/` and Artifact Directory)

The following research plots were generated directly from empirical data without scaling manipulation:

| Figure Name | File Path | Description |
| :--- | :--- | :--- |
| **Average Waiting Time** | [`phase_n_waiting_time.png`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_n_waiting_time.png) | Bar chart comparing mean completed-vehicle delay across Fixed-Time, Adaptive, QUBO Exact, and QAOA. |
| **Average Queue Length** | [`phase_n_queue_length.png`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_n_queue_length.png) | Mean observed queue lengths across all four controllers under Low, Normal, and High traffic conditions. |
| **Network Throughput** | [`phase_n_throughput.png`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_n_throughput.png) | Completed vehicles per hour across demand levels and control policies. |
| **QAOA Objective Gap** | [`phase_n_qaoa_objective_gap.png`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_n_qaoa_objective_gap.png) | Histogram showing the distribution of absolute objective gaps $|E_{\text{QAOA}} - E_{\text{exact}}|$ across 240 optimization decisions. |
| **QAOA Recovery Rate** | [`phase_n_qaoa_recovery_rate.png`](file:///c:/Users/anand/Quantum-Enhanced-Adaptive-Urban-Traffic-Optimization-1/data/results/phase_n_qaoa_recovery_rate.png) | Bar chart illustrating exact classical optimum recovery percentage by traffic demand scenario ($100\%$ Low, $92.5\%$ Normal, $87.5\%$ High). |

---

## 3. UI & Dashboard Verification Artifacts

- **Command Dashboard Screenshot**: [`flowq_command_dashboard_1789847368368.png`](file:///C:/Users/anand/.gemini/antigravity-ide/brain/387bf05f-ea03-4342-b6ab-ae1e863a2c10/flowq_command_dashboard_1789847368368.png)
  - Full-screen high-resolution capture of the live FlowQ Quantum Mobility Command dashboard displaying 8-junction grid telemetry, emergency controls, dynamic events, sustainability metrics, and QAOA inspector.
- **End-to-End Walkthrough Recording**: [`phase_o_dashboard_eval_1789846201572.webp`](file:///C:/Users/anand/.gemini/antigravity-ide/brain/387bf05f-ea03-4342-b6ab-ae1e863a2c10/phase_o_dashboard_eval_1789846201572.webp)
  - Complete WebP interaction recording demonstrating tab navigation, emergency corridor dispatch, progression, release, dynamic event injection, and prototype vision stream.
