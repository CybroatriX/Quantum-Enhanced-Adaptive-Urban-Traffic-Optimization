# FlowQ Web Digital Twin

Run from the project root:

```powershell
npm start
```

Open `http://localhost:4173`. Run verification with `npm test`.

The server has no third-party npm dependencies. The dashboard models eight
connected intersections, multi-path traffic, QUBO/adaptive/fixed signals,
pedestrians, three disruption types, an emergency green corridor, fuel and CO2,
and a live fixed-vs-hybrid comparison. Files in `public` also work as a static
demonstration by falling back to the in-browser QUBO solver when the backend API
is unavailable.
