"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const vm = require("node:vm");

const SimulationCore = require("../web/public/simulation-core.js");
const TrafficOptimizer = require("../web/public/optimizer.js");

class ClassList {
  constructor() { this.values = new Set(); }
  add(...v) { v.forEach(x => this.values.add(x)); }
  remove(...v) { v.forEach(x => this.values.delete(x)); }
  toggle(v, force) {
    if (force === true) this.values.add(v);
    else if (force === false) this.values.delete(v);
    else if (this.values.has(v)) this.values.delete(v);
    else this.values.add(v);
  }
}

function createMockContext() {
  const grad = () => ({ addColorStop() {} });
  return new Proxy({}, {
    get(t, p) {
      if (p === "createRadialGradient" || p === "createLinearGradient") return grad;
      if (["fillRect", "stroke", "arc", "fillText", "strokeRect"].includes(p)) return () => {};
      if (["setTransform", "beginPath", "moveTo", "lineTo", "fill", "save", "restore", "translate", "scale", "rotate", "setLineDash", "clearRect"].includes(p)) return () => {};
      return t[p];
    },
    set(t, p, v) { t[p] = v; return true; }
  });
}

class FakeElement {
  constructor(id) {
    this.id = id;
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.checked = true;
    this.hidden = false;
    this.style = {};
    this.classList = new ClassList();
    this.listeners = {};
    this.parentElement = { classList: new ClassList() };
    this.options = [{ text: "QUBO adaptive" }];
    this.selectedIndex = 0;
    this.width = 1100;
    this.height = 800;
    this._context = createMockContext();
    this._lights = ["red", "yellow", "green"].map(c => ({ classList: new ClassList(), color: c }));
  }
  getContext() { return this._context; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 1100, height: 800 }; }
  addEventListener(type, cb) { (this.listeners[type] ||= []).push(cb); }
  fire(type, extra = {}) { for (const cb of this.listeners[type] || []) cb({ target: this, ...extra }); }
  querySelectorAll(selector) {
    if (selector === "i") return this._lights;
    if (selector === ".network-card") return [new FakeElement("card0"), new FakeElement("card1"), new FakeElement("card2"), new FakeElement("card3")];
    return [];
  }
  querySelector(sel) { return this._lights.find(l => `.${l.color}` === sel) || null; }
  setPointerCapture() {}
}

const root = path.join(__dirname, "..", "web", "public");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const code = fs.readFileSync(path.join(root, "app.js"), "utf8");
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
const elements = new Map(ids.map(id => [id, new FakeElement(id)]));

const raf = [];
const windowObject = {
  SimulationCore,
  TrafficOptimizer,
  devicePixelRatio: 1,
  addEventListener() {}
};
const sandbox = {
  window: windowObject,
  document: {
    getElementById(id) { return elements.get(id) || null; },
    querySelectorAll() { return []; }
  },
  location: { protocol: "file:" },
  performance: { now: () => 0 },
  requestAnimationFrame(cb) { raf.push(cb); return raf.length; },
  setTimeout(cb) { cb(); return 1; },
  clearTimeout() {},
  fetch: async () => { throw new Error("No network"); },
  console, Math, Map, Set, Array, Object, Number, String
};

vm.runInNewContext(code, sandbox, { filename: "app.js" });

console.log("=== RUNNING SIGNAL VERIFICATION SUITE ACROSS J1 - J4 ===");

const totalViolations = {
  northSouthSimultaneousGreen: 0,
  eastWestSimultaneousGreen: 0,
  multipleGreens: 0,
  multipleYellows: 0,
  greenAndYellowSimultaneous: 0
};

const intersectionStats = [
  { id: 0, name: "J1 Harbor Gate", observedPhases: new Set(), greenTransitions: [] },
  { id: 1, name: "J2 Civic Square", observedPhases: new Set(), greenTransitions: [] },
  { id: 2, name: "J3 Market Circle", observedPhases: new Set(), greenTransitions: [] },
  { id: 3, name: "J4 Tech Park", observedPhases: new Set(), greenTransitions: [] }
];

let now = 0;
for (let frame = 0; frame < 12000; frame += 1) {
  const cb = raf.shift();
  if (cb) { now += 16.667; cb(now); }

  const snap = windowObject.FlowQDiagnostics.snapshot();
  for (const s of snap.signals) {
    if (s.id >= 4) continue;
    const stats = intersectionStats[s.id];
    stats.observedPhases.add(s.phase);

    const n = s.northColor;
    const so = s.southColor;
    const e = s.eastColor;
    const w = s.westColor;

    const greens = [n, so, e, w].filter(c => c === "green");
    const yellows = [n, so, e, w].filter(c => c === "yellow");

    // Track active green direction
    if (greens.length === 1) {
      const activeDir = n === "green" ? "NORTH" : (so === "green" ? "SOUTH" : (e === "green" ? "EAST" : "WEST"));
      if (stats.greenTransitions.length === 0 || stats.greenTransitions[stats.greenTransitions.length - 1] !== activeDir) {
        stats.greenTransitions.push(activeDir);
      }
    }

    // Check violations
    if (n === "green" && so === "green") {
      totalViolations.northSouthSimultaneousGreen += 1;
    }
    if (e === "green" && w === "green") {
      totalViolations.eastWestSimultaneousGreen += 1;
    }
    if (greens.length > 1) {
      totalViolations.multipleGreens += 1;
    }
    if (yellows.length > 1) {
      totalViolations.multipleYellows += 1;
    }
    if (greens.length > 0 && yellows.length > 0) {
      totalViolations.greenAndYellowSimultaneous += 1;
    }
  }
}

console.log("\n--- VIOLATION AUDIT ---");
console.log(`North + South GREEN together: ${totalViolations.northSouthSimultaneousGreen} (MUST BE 0)`);
console.log(`East + West GREEN together:   ${totalViolations.eastWestSimultaneousGreen} (MUST BE 0)`);
console.log(`Any two GREEN lights together: ${totalViolations.multipleGreens} (MUST BE 0)`);
console.log(`Multiple YELLOW lights:       ${totalViolations.multipleYellows} (MUST BE 0)`);
console.log(`Simultaneous GREEN + YELLOW:  ${totalViolations.greenAndYellowSimultaneous} (MUST BE 0)`);

assert.equal(totalViolations.northSouthSimultaneousGreen, 0);
assert.equal(totalViolations.eastWestSimultaneousGreen, 0);
assert.equal(totalViolations.multipleGreens, 0);
assert.equal(totalViolations.multipleYellows, 0);
assert.equal(totalViolations.greenAndYellowSimultaneous, 0);

console.log("\n--- INTERSECTION INSPECTION ---");
for (const stat of intersectionStats) {
  console.log(`\nIntersection: J${stat.id + 1} (${stat.name})`);
  console.log(`Observed Phases: ${[...stat.observedPhases].join(", ")}`);
  console.log(`Observed Green Transition Sequence: ${stat.greenTransitions.slice(0, 12).join(" -> ")} ...`);

  assert.ok(stat.observedPhases.has("NORTH_GREEN"), `J${stat.id + 1} must observe NORTH_GREEN`);
  assert.ok(stat.observedPhases.has("SOUTH_GREEN"), `J${stat.id + 1} must observe SOUTH_GREEN`);
  assert.ok(stat.observedPhases.has("EAST_GREEN"), `J${stat.id + 1} must observe EAST_GREEN`);
  assert.ok(stat.observedPhases.has("WEST_GREEN"), `J${stat.id + 1} must observe WEST_GREEN`);

  // Verify transition sequence follows NORTH -> SOUTH -> EAST -> WEST cycle
  for (let i = 0; i < stat.greenTransitions.length - 1; i += 1) {
    const cur = stat.greenTransitions[i];
    const nxt = stat.greenTransitions[i + 1];
    if (cur === "NORTH") assert.equal(nxt, "SOUTH", `After NORTH, green must switch to SOUTH, got ${nxt}`);
    else if (cur === "SOUTH") assert.equal(nxt, "EAST", `After SOUTH, green must switch to EAST, got ${nxt}`);
    else if (cur === "EAST") assert.equal(nxt, "WEST", `After EAST, green must switch to WEST, got ${nxt}`);
    else if (cur === "WEST") assert.equal(nxt, "NORTH", `After WEST, green must switch to NORTH, got ${nxt}`);
  }
  console.log(`[PASS] J${stat.id + 1}: Strictly ONE direction green at a time with correct cycle order!`);
}

console.log("\n=== ALL CHECKS PASSED SUCCESSFULLY ===");
