"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const SimulationCore = require("../public/simulation-core.js");
const TrafficOptimizer = require("../public/optimizer.js");

class ClassList {
  constructor() { this.values = new Set(); }
  add(...values) { values.forEach(value => this.values.add(value)); }
  remove(...values) { values.forEach(value => this.values.delete(value)); }
  toggle(value, force) {
    if (force === true) this.values.add(value);
    else if (force === false) this.values.delete(value);
    else if (this.values.has(value)) this.values.delete(value);
    else this.values.add(value);
  }
}

function createContext(draws) {
  const gradient = () => ({ addColorStop() {} });
  return new Proxy({}, {
    get(target, property) {
      if (property === "createRadialGradient" || property === "createLinearGradient") return gradient;
      if (["fillRect", "stroke", "arc", "fillText", "strokeRect"].includes(property)) return () => { draws[property] = (draws[property] || 0) + 1; };
      if (["setTransform", "beginPath", "moveTo", "lineTo", "fill", "save", "restore", "translate", "scale", "rotate", "setLineDash", "clearRect"].includes(property)) return () => {};
      return target[property];
    },
    set(target, property, value) { target[property] = value; return true; }
  });
}

class FakeElement {
  constructor(id, draws) {
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
    this.options = [{ text: "QUBO adaptive" }, { text: "Pressure adaptive" }, { text: "Fixed timing" }];
    this.selectedIndex = 0;
    this.width = 1100;
    this.height = 800;
    this._context = createContext(draws);
    this._lights = ["red", "yellow", "green"].map(color => ({ classList: new ClassList(), color }));
  }
  getContext() { return this._context; }
  getBoundingClientRect() { return this.id === "cameraCanvas" ? { left: 0, top: 0, width: 320, height: 150 } : { left: 0, top: 0, width: 1100, height: 800 }; }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  fire(type, extra = {}) {
    const event = { target: this, clientX: 550, clientY: 400, pointerId: 1, deltaY: -100, key: "", preventDefault() {}, ...extra };
    for (const callback of this.listeners[type] || []) callback(event);
  }
  querySelectorAll(selector) { return selector === "i" ? this._lights : []; }
  querySelector(selector) { return this._lights.find(light => `.${light.color}` === selector) || null; }
  setPointerCapture() {}
}

test("browser simulation runs controls and high-demand traffic without overlap", async () => {
  const root = path.join(__dirname, "..", "public");
  const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
  const code = fs.readFileSync(path.join(root, "app.js"), "utf8");
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
  const draws = {};
  const elements = new Map(ids.map(id => [id, new FakeElement(id, draws)]));
  const defaults = {
    seedInput: "COIMBATORE-08", controllerSelect: "qubo", demandRange: "180",
    pedestrianRange: "35", speedRange: "1"
  };
  Object.entries(defaults).forEach(([id, value]) => { elements.get(id).value = value; });
  const mapActions = [
    "congestionBtn", "accidentBtn", "closureBtn", "ambulanceBtn", "hospitalBtn", "inspectBtn"
  ].map(id => elements.get(id));
  const raf = [];
  const windowObject = {
    SimulationCore,
    TrafficOptimizer,
    devicePixelRatio: 1,
    addEventListener() {}
  };
  const documentObject = {
    getElementById(id) { return elements.get(id) || null; },
    querySelectorAll(selector) { return selector === ".map-action" ? mapActions : []; }
  };
  const sandbox = {
    window: windowObject,
    document: documentObject,
    location: { protocol: "file:" },
    performance: { now: () => 0 },
    requestAnimationFrame(callback) { raf.push(callback); return raf.length; },
    setTimeout(callback) { callback(); return 1; },
    clearTimeout() {},
    fetch: async () => { throw new Error("Network should not be used for file mode."); },
    console,
    Math,
    Map,
    Set,
    Array,
    Object,
    Number,
    String
  };

  vm.runInNewContext(code, sandbox, { filename: "app.js" });
  const generated = SimulationCore.generateCity("COIMBATORE-08");
  const fittedZoom = Math.min((1100 - 80) / generated.world.width, (800 - 125) / generated.world.height);
  const fittedX = (1100 - generated.world.width * fittedZoom) / 2;
  const fittedY = (800 - generated.world.height * fittedZoom) / 2 + 24;
  const screenPoint = point => ({ clientX: fittedX + point.x * fittedZoom, clientY: fittedY + point.y * fittedZoom });
  elements.get("demandRange").value = "360";
  elements.get("demandRange").fire("input");
  elements.get("speedRange").value = "4";
  elements.get("speedRange").fire("input");
  elements.get("controllerSelect").value = "adaptive";
  elements.get("controllerSelect").selectedIndex = 1;
  elements.get("controllerSelect").fire("change");
  elements.get("controllerSelect").value = "fixed";
  elements.get("controllerSelect").selectedIndex = 2;
  elements.get("controllerSelect").fire("change");
  elements.get("controllerSelect").value = "qubo";
  elements.get("controllerSelect").selectedIndex = 0;
  elements.get("controllerSelect").fire("change");
  elements.get("hospitalBtn").fire("click");
  elements.get("cityCanvas").fire("pointerdown", screenPoint(generated.nodes[2]));
  elements.get("cityCanvas").fire("pointerup", screenPoint(generated.nodes[2]));
  elements.get("ambulanceBtn").fire("click");
  elements.get("cityCanvas").fire("pointerdown", screenPoint(generated.nodes[7]));
  elements.get("cityCanvas").fire("pointerup", screenPoint(generated.nodes[7]));
  elements.get("accidentBtn").fire("click");
  const incidentEdge = generated.edges[8];
  const edgeMidpoint = {
    x: (generated.nodes[incidentEdge.a].x + generated.nodes[incidentEdge.b].x) / 2,
    y: (generated.nodes[incidentEdge.a].y + generated.nodes[incidentEdge.b].y) / 2
  };
  elements.get("cityCanvas").fire("pointerdown", screenPoint(edgeMidpoint));
  elements.get("cityCanvas").fire("pointerup", screenPoint(edgeMidpoint));
  elements.get("zoomInBtn").fire("click");
  elements.get("zoomOutBtn").fire("click");
  elements.get("fitBtn").fire("click");
  elements.get("cityCanvas").fire("wheel");

  let now = 0;
  for (let frame = 0; frame < 3200; frame += 1) {
    const callback = raf.shift();
    assert.ok(callback, "animation loop must continue");
    now += 16.667;
    callback(now);
    if (frame % 25 === 0) await Promise.resolve();
  }

  assert.notEqual(elements.get("simClock").textContent, "00:00:00");
  const diagnostics = windowObject.FlowQDiagnostics.snapshot();
  assert.equal(diagnostics.overlaps, 0, JSON.stringify(diagnostics.vehicles));
  assert.ok(Number(elements.get("vehicleMetric").textContent.replaceAll(",", "")) > 100);
  assert.ok(draws.fillRect > 100_000);
  assert.ok(draws.stroke > 100_000);
  assert.match(elements.get("algorithmStatus").textContent, /QUBO states evaluated/);
  assert.equal(elements.get("backendStatus").textContent, "LOCAL ENGINE");
  assert.match(elements.get("eventStream").innerHTML, /Hospital relocated/);
  assert.match(elements.get("eventStream").innerHTML, /Ambulance/);
  assert.match(elements.get("eventStream").innerHTML, /Accident reported/);
});
