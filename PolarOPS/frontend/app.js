/**
 * PolarOPS - Frontend JavaScript Controller
 * Autonomous Microgrid Digital Twin for Maitri & Bharati Stations.
 * Handles WebSockets, Particle Vector Flow Canvas, Chart.js graphs, AI Chat, and Commander Overrides.
 */

// -------------------------------------------------------------
// State Management
// -------------------------------------------------------------
const state = {
  stationId: "MAITRI",
  mode: "DEMO_MODE",
  ws: null,
  wsConnected: false,
  reconnectAttempts: 0,
  latestData: null,
  tripGen1: false,
  faultBess: false,
};

// -------------------------------------------------------------
// Chart.js Instances
// -------------------------------------------------------------
let forecastChartInstance = null;
let dispatchDonutInstance = null;

// -------------------------------------------------------------
// Energy Flow Matrix Canvas Animation Engine
// -------------------------------------------------------------
const canvas = document.getElementById("energy-flow-canvas");
const ctx = canvas.getContext("2d");

// Particle System State
let particles = [];
const PARTICLE_SPEED_BASE = 1.2;

function resizeCanvas() {
  if (!canvas) return;
  canvas.width = canvas.parentElement.clientWidth;
  canvas.height = canvas.parentElement.clientHeight || 280;
}
window.addEventListener("resize", () => {
  resizeCanvas();
  if (forecastChartInstance) forecastChartInstance.resize();
  if (dispatchDonutInstance) dispatchDonutInstance.resize();
});
resizeCanvas();

// State additions
state.selectedHorizon = "24 Hours";
state.windRotorAngle = 0;

// Source & Destination Topology Coordinates (Normalized [0..1])
const nodes = {
  wind: { x: 0.12, y: 0.20, label: "WINDMILL", type: "wind", color: "#38bdf8", sublabel: "Array" },
  solar: { x: 0.12, y: 0.42, label: "SOLAR PV", type: "solar", color: "#fbbf24", sublabel: "Bifacial" },
  bess: { x: 0.12, y: 0.64, label: "BATTERY BESS", type: "battery", color: "#34d399", sublabel: "LiFePO4" },
  diesel: { x: 0.12, y: 0.86, label: "GENERATOR", type: "diesel", color: "#f43f5e", sublabel: "Diesel CHP" },
  hub: { x: 0.52, y: 0.48, label: "GRID HUB", type: "hub", color: "#06b6d4", sublabel: "Busbar" },
  elec_load: { x: 0.88, y: 0.32, label: "STATION LOAD", type: "elec_load", color: "#38bdf8", sublabel: "Electrical" },
  thermal_load: { x: 0.88, y: 0.72, label: "CHP HEATING", type: "thermal_load", color: "#fb7185", sublabel: "Thermal" },
};

// -------------------------------------------------------------
// Dedicated, Intuitive Icon Renderers (Works in Dark & Light)
// -------------------------------------------------------------

function drawWindmillIcon(ctx, x, y, size, windSpeed, color) {
  ctx.save();
  ctx.translate(x, y);

  // Turbine Tower (Tapered Mast)
  ctx.beginPath();
  ctx.moveTo(-size * 0.15, size * 0.9);
  ctx.lineTo(-size * 0.06, -size * 0.1);
  ctx.lineTo(size * 0.06, -size * 0.1);
  ctx.lineTo(size * 0.15, size * 0.9);
  ctx.closePath();
  ctx.fillStyle = "rgba(148, 163, 184, 0.4)";
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.2;
  ctx.stroke();

  // Rotor Hub
  const hubY = -size * 0.1;
  ctx.beginPath();
  ctx.arc(0, hubY, size * 0.18, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();

  // 3 Aerodynamic Blades dynamically rotating based on wind speed
  state.windRotorAngle += Math.max(0.01, (windSpeed || 8.0) * 0.008);
  const bladeLen = size * 0.85;

  for (let i = 0; i < 3; i++) {
    const angle = state.windRotorAngle + (i * 2 * Math.PI) / 3;
    ctx.save();
    ctx.translate(0, hubY);
    ctx.rotate(angle);

    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.quadraticCurveTo(size * 0.14, -bladeLen * 0.5, 0, -bladeLen);
    ctx.quadraticCurveTo(-size * 0.08, -bladeLen * 0.5, 0, 0);
    ctx.fillStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 6;
    ctx.fill();
    ctx.restore();
  }

  ctx.restore();
}

function drawSolarIcon(ctx, x, y, size, solarWm2, color) {
  ctx.save();
  ctx.translate(x, y);

  // 1. Radiant Sun
  const sunRadius = size * 0.38;
  ctx.beginPath();
  ctx.arc(0, -size * 0.25, sunRadius, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.shadowColor = color;
  ctx.shadowBlur = 10;
  ctx.fill();

  // 8 Sun Rays
  const rayLen = size * 0.22;
  for (let i = 0; i < 8; i++) {
    const ang = (i * Math.PI) / 4;
    const rx1 = Math.cos(ang) * (sunRadius + 2);
    const ry1 = -size * 0.25 + Math.sin(ang) * (sunRadius + 2);
    const rx2 = Math.cos(ang) * (sunRadius + rayLen);
    const ry2 = -size * 0.25 + Math.sin(ang) * (sunRadius + rayLen);

    ctx.beginPath();
    ctx.moveTo(rx1, ry1);
    ctx.lineTo(rx2, ry2);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.8;
    ctx.stroke();
  }

  // 2. Angled Photovoltaic Panel Grid below Sun
  const pw = size * 1.3;
  const ph = size * 0.55;
  const py = size * 0.35;

  // Trapezoidal perspective panel
  ctx.beginPath();
  ctx.moveTo(-pw * 0.42, py - ph * 0.35);
  ctx.lineTo(pw * 0.42, py - ph * 0.35);
  ctx.lineTo(pw * 0.55, py + ph * 0.45);
  ctx.lineTo(-pw * 0.55, py + ph * 0.45);
  ctx.closePath();
  ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.6;
  ctx.stroke();

  // Internal PV Silicon Wafer Grid Lines
  ctx.beginPath();
  ctx.moveTo(0, py - ph * 0.35);
  ctx.lineTo(0, py + ph * 0.45);
  ctx.moveTo(-pw * 0.48, py + ph * 0.05);
  ctx.lineTo(pw * 0.48, py + ph * 0.05);
  ctx.strokeStyle = `${color}99`;
  ctx.lineWidth = 1.0;
  ctx.stroke();

  ctx.restore();
}

function drawBatteryIcon(ctx, x, y, size, socPct, color) {
  ctx.save();
  ctx.translate(x, y);

  const bw = size * 1.1;
  const bh = size * 1.5;
  const r = 3;

  // Battery Top Terminal Anode/Cathode Cap
  ctx.beginPath();
  ctx.roundRect(-bw * 0.25, -bh * 0.5 - 3, bw * 0.5, 4, 1.5);
  ctx.fillStyle = color;
  ctx.fill();

  // Battery Main Casing
  ctx.beginPath();
  ctx.roundRect(-bw * 0.5, -bh * 0.5, bw, bh, r);
  ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.8;
  ctx.stroke();

  // Segmented Energy Fill Levels (3 segments proportional to SoC)
  const soc = Math.max(0, Math.min(100, socPct || 75));
  const segH = (bh - 8) / 3;
  const activeSegments = soc > 65 ? 3 : soc > 30 ? 2 : 1;
  const segColor = soc <= 20 ? "#f43f5e" : soc < 50 ? "#fbbf24" : color;

  for (let s = 0; s < 3; s++) {
    const sy = bh * 0.5 - 4 - (s + 1) * segH;
    if (s < activeSegments) {
      ctx.beginPath();
      ctx.roundRect(-bw * 0.4, sy + 1.5, bw * 0.8, segH - 3, 1.5);
      ctx.fillStyle = segColor;
      ctx.shadowColor = segColor;
      ctx.shadowBlur = 4;
      ctx.fill();
    }
  }

  // Centered Sharp Lightning Bolt Glyph
  ctx.shadowBlur = 0;
  ctx.beginPath();
  ctx.moveTo(size * 0.05, -size * 0.35);
  ctx.lineTo(-size * 0.18, 0);
  ctx.lineTo(0, 0);
  ctx.lineTo(-size * 0.05, size * 0.35);
  ctx.lineTo(size * 0.18, 0);
  ctx.lineTo(0, 0);
  ctx.closePath();
  ctx.fillStyle = "#ffffff";
  ctx.fill();

  ctx.restore();
}

function drawGeneratorIcon(ctx, x, y, size, isRunning, color) {
  ctx.save();
  ctx.translate(x, y);

  const gw = size * 1.5;
  const gh = size * 1.1;

  // Generator Main Skid & Engine Block Housing
  ctx.beginPath();
  ctx.roundRect(-gw * 0.5, -gh * 0.45, gw, gh * 0.9, 3);
  ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.8;
  ctx.stroke();

  // Engine Cooling Louvers / Heat Radiator Slits
  ctx.strokeStyle = `${color}99`;
  ctx.lineWidth = 1.2;
  for (let i = -1; i <= 1; i++) {
    const lx = -gw * 0.28 + i * 5;
    ctx.beginPath();
    ctx.moveTo(lx, -gh * 0.25);
    ctx.lineTo(lx, gh * 0.25);
    ctx.stroke();
  }

  // Top Exhaust Stack Manifold
  ctx.beginPath();
  ctx.rect(gw * 0.2, -gh * 0.5 - 5, gw * 0.16, 5);
  ctx.fillStyle = color;
  ctx.fill();

  // Thermal CHP Exhaust Waves (if running)
  if (isRunning) {
    const waveOffset = (Date.now() * 0.004) % 6;
    ctx.beginPath();
    ctx.arc(gw * 0.28, -gh * 0.5 - 9 - waveOffset, 3, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(251, 113, 133, 0.6)";
    ctx.fill();
  }

  // Industrial Gear / Crankshaft Emblem in Center
  ctx.beginPath();
  ctx.arc(gw * 0.15, 0, size * 0.28, 0, Math.PI * 2);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(gw * 0.15, 0, size * 0.1, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();

  ctx.restore();
}

function drawHubIcon(ctx, x, y, size, color) {
  ctx.save();
  ctx.translate(x, y);

  // Outer Pulsing High-Voltage Transformer Ring
  const pulse = 1.0 + 0.08 * Math.sin(Date.now() * 0.005);
  ctx.beginPath();
  ctx.arc(0, 0, size * 0.8 * pulse, 0, Math.PI * 2);
  ctx.strokeStyle = `${color}55`;
  ctx.lineWidth = 2.0;
  ctx.stroke();

  // Middle Octagon / Busbar Base
  ctx.beginPath();
  ctx.arc(0, 0, size * 0.55, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(11, 18, 33, 0.9)";
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.8;
  ctx.stroke();

  // 4-Way Cross Busbar Junction Points
  ctx.beginPath();
  ctx.moveTo(-size * 0.35, 0);
  ctx.lineTo(size * 0.35, 0);
  ctx.moveTo(0, -size * 0.35);
  ctx.lineTo(0, size * 0.35);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.0;
  ctx.stroke();

  // Glowing Core
  ctx.beginPath();
  ctx.arc(0, 0, size * 0.18, 0, Math.PI * 2);
  ctx.fillStyle = "#ffffff";
  ctx.shadowColor = color;
  ctx.shadowBlur = 10;
  ctx.fill();

  ctx.restore();
}

function drawStationLoadIcon(ctx, x, y, size, color) {
  ctx.save();
  ctx.translate(x, y);

  // Geodesic Polar Research Station Dome
  ctx.beginPath();
  ctx.arc(0, size * 0.15, size * 0.65, Math.PI, 0);
  ctx.closePath();
  ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.8;
  ctx.stroke();

  // Antenna Mast on Station
  ctx.beginPath();
  ctx.moveTo(0, -size * 0.5);
  ctx.lineTo(0, -size * 0.95);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Antenna Signal Rings
  ctx.beginPath();
  ctx.arc(0, -size * 0.95, 3, 0, Math.PI * 2);
  ctx.fillStyle = "#38bdf8";
  ctx.fill();

  ctx.restore();
}

function drawThermalLoadIcon(ctx, x, y, size, color) {
  ctx.save();
  ctx.translate(x, y);

  // Heating Radiator Base Housing
  ctx.beginPath();
  ctx.roundRect(-size * 0.7, -size * 0.2, size * 1.4, size * 0.8, 2);
  ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.8;
  ctx.stroke();

  // Radiator Heating Coils
  ctx.strokeStyle = `${color}bb`;
  ctx.lineWidth = 1.4;
  for (let i = -3; i <= 3; i++) {
    const rx = i * 4.5;
    ctx.beginPath();
    ctx.moveTo(rx, -size * 0.12);
    ctx.lineTo(rx, size * 0.5);
    ctx.stroke();
  }

  // Ascending Convective Heat Waves
  const offset = (Date.now() * 0.003) % 4;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  for (let i = -1; i <= 1; i++) {
    const hx = i * 8;
    ctx.beginPath();
    ctx.moveTo(hx - 2, -size * 0.35 - offset);
    ctx.quadraticCurveTo(hx + 3, -size * 0.55 - offset, hx - 2, -size * 0.75 - offset);
    ctx.stroke();
  }

  ctx.restore();
}

class Particle {
  constructor(sourceKey, targetKey, color, speedMultiplier = 1.0) {
    this.sourceKey = sourceKey;
    this.targetKey = targetKey;
    this.color = color;
    this.progress = Math.random();
    this.speed = (0.004 + Math.random() * 0.003) * speedMultiplier * PARTICLE_SPEED_BASE;
    this.size = 2.0 + Math.random() * 2.0;
  }

  update() {
    this.progress += this.speed;
    if (this.progress > 1.0) {
      this.progress = 0;
    }
  }

  draw(ctx, width, height) {
    const s = nodes[this.sourceKey];
    const t = nodes[this.targetKey];
    const sx = s.x * width;
    const sy = s.y * height;
    const tx = t.x * width;
    const ty = t.y * height;

    // Cubic bezier smooth curve
    const cp1x = sx + (tx - sx) * 0.5;
    const cp1y = sy;
    const cp2x = sx + (tx - sx) * 0.5;
    const cp2y = ty;

    const p = this.progress;
    const x = Math.pow(1 - p, 3) * sx + 3 * Math.pow(1 - p, 2) * p * cp1x + 3 * (1 - p) * Math.pow(p, 2) * cp2x + Math.pow(p, 3) * tx;
    const y = Math.pow(1 - p, 3) * sy + 3 * Math.pow(1 - p, 2) * p * cp1y + 3 * (1 - p) * Math.pow(p, 2) * cp2y + Math.pow(p, 3) * ty;

    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, this.size, 0, Math.PI * 2);
    ctx.fillStyle = this.color;
    ctx.shadowColor = this.color;
    ctx.shadowBlur = 8;
    ctx.fill();
    ctx.restore();
  }
}

function updateParticlePipes(dispatch) {
  const pWind = dispatch?.p_wind_kw || 0;
  const pSolar = dispatch?.p_solar_kw || 0;
  const pBess = dispatch?.p_battery_discharge_kw || 0;
  const pDiesel = (dispatch?.p_diesel_1_kw || 0) + (dispatch?.p_diesel_2_kw || 0);
  const qChp = dispatch?.q_chp_thermal_kwth || 0;

  const countWind = Math.min(24, Math.floor(pWind / 4.5));
  const countSolar = Math.min(20, Math.floor(pSolar / 4.0));
  const countBess = Math.min(20, Math.floor(pBess / 3.0));
  const countDiesel = Math.min(26, Math.floor(pDiesel / 4.0));
  const countElec = Math.min(30, Math.floor((pWind + pSolar + pBess + pDiesel) / 4.5));
  const countChp = Math.min(22, Math.floor(qChp / 4.0));

  const newParticles = [];
  for (let i = 0; i < countWind; i++) newParticles.push(new Particle("wind", "hub", nodes.wind.color, 1.2));
  for (let i = 0; i < countSolar; i++) newParticles.push(new Particle("solar", "hub", nodes.solar.color, 1.0));
  for (let i = 0; i < countBess; i++) newParticles.push(new Particle("bess", "hub", nodes.bess.color, 1.1));
  for (let i = 0; i < countDiesel; i++) newParticles.push(new Particle("diesel", "hub", nodes.diesel.color, 1.3));
  
  for (let i = 0; i < countElec; i++) newParticles.push(new Particle("hub", "elec_load", "#38bdf8", 1.4));
  for (let i = 0; i < countChp; i++) newParticles.push(new Particle("diesel", "thermal_load", "#fb7185", 1.1));

  particles = newParticles;
}

function renderEnergyFlow() {
  if (!canvas || !ctx) return;
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  const drawPipe = (s, t, color, active) => {
    const sx = s.x * w;
    const sy = s.y * h;
    const tx = t.x * w;
    const ty = t.y * h;
    const cp1x = sx + (tx - sx) * 0.5;
    const cp2x = sx + (tx - sx) * 0.5;

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.bezierCurveTo(cp1x, sy, cp2x, ty, tx, ty);
    ctx.strokeStyle = active ? `${color}55` : "rgba(51, 65, 85, 0.22)";
    ctx.lineWidth = active ? 2.6 : 1.2;
    ctx.stroke();
    ctx.restore();
  };

  const dispatch = state.latestData?.dispatch;
  const telem = state.latestData?.telemetry;
  const pWind = (dispatch?.p_wind_kw || 0) > 0;
  const pSolar = (dispatch?.p_solar_kw || 0) > 0;
  const pBess = (dispatch?.p_battery_discharge_kw || 0) > 0;
  const pDiesel = ((dispatch?.p_diesel_1_kw || 0) + (dispatch?.p_diesel_2_kw || 0)) > 0;

  // Connecting Power Vectors
  drawPipe(nodes.wind, nodes.hub, nodes.wind.color, pWind);
  drawPipe(nodes.solar, nodes.hub, nodes.solar.color, pSolar);
  drawPipe(nodes.bess, nodes.hub, nodes.bess.color, pBess);
  drawPipe(nodes.diesel, nodes.hub, nodes.diesel.color, pDiesel);
  drawPipe(nodes.hub, nodes.elec_load, "#38bdf8", true);
  drawPipe(nodes.diesel, nodes.thermal_load, "#fb7185", (dispatch?.q_chp_thermal_kwth || 0) > 0);

  // Animated Particles
  for (let i = 0; i < particles.length; i++) {
    particles[i].update();
    particles[i].draw(ctx, w, h);
  }

  // Render Dedicated Intuitive Node Icons
  Object.keys(nodes).forEach((key) => {
    const node = nodes[key];
    const nx = node.x * w;
    const ny = node.y * h;
    const iconSize = 18;

    // Glowing Circular Backdrop
    ctx.save();
    ctx.beginPath();
    ctx.arc(nx, ny, 22, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(7, 11, 20, 0.88)";
    ctx.shadowColor = node.color;
    ctx.shadowBlur = 14;
    ctx.fill();
    ctx.strokeStyle = `${node.color}88`;
    ctx.lineWidth = 1.6;
    ctx.stroke();
    ctx.restore();

    // Render Specific Vector Icon for each asset
    if (node.type === "wind") {
      drawWindmillIcon(ctx, nx, ny, iconSize, telem?.wind_speed_ms || 10.0, node.color);
    } else if (node.type === "solar") {
      drawSolarIcon(ctx, nx, ny, iconSize, telem?.solar_irradiance_wm2 || 120.0, node.color);
    } else if (node.type === "battery") {
      drawBatteryIcon(ctx, nx, ny, iconSize, telem?.battery_soc_pct || 75.0, node.color);
    } else if (node.type === "diesel") {
      drawGeneratorIcon(ctx, nx, ny, iconSize, pDiesel, node.color);
    } else if (node.type === "hub") {
      drawHubIcon(ctx, nx, ny, iconSize, node.color);
    } else if (node.type === "elec_load") {
      drawStationLoadIcon(ctx, nx, ny, iconSize, node.color);
    } else if (node.type === "thermal_load") {
      drawThermalLoadIcon(ctx, nx, ny, iconSize, node.color);
    }

    // Node Text & Sublabel (Crisp in dark & light)
    ctx.save();
    ctx.font = "bold 10px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#f1f5f9";
    ctx.textAlign = key.startsWith("elec") || key.startsWith("thermal") ? "left" : (key === "hub" ? "center" : "right");
    const labelX = key.startsWith("elec") || key.startsWith("thermal") ? nx + 28 : (key === "hub" ? nx : nx - 28);
    ctx.fillText(node.label, labelX, ny - 1);

    ctx.font = "normal 8.5px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#94a3b8";
    ctx.fillText(node.sublabel, labelX, ny + 11);
    ctx.restore();
  });

  requestAnimationFrame(renderEnergyFlow);
}

requestAnimationFrame(renderEnergyFlow);

// -------------------------------------------------------------
// Chart.js Setup & Rendering
// -------------------------------------------------------------
function initForecastChart() {
  const chartEl = document.getElementById("forecast-chart");
  if (!chartEl) return;

  const labels = Array.from({ length: 24 }, (_, i) => `${i}:00`);

  forecastChartInstance = new Chart(chartEl, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Electrical Load (kWe)",
          data: [],
          borderColor: "#38bdf8",
          backgroundColor: "rgba(56, 189, 248, 0.1)",
          borderWidth: 2,
          tension: 0.3,
          pointRadius: 1,
          fill: false,
        },
        {
          label: "Thermal Demand (kWth)",
          data: [],
          borderColor: "#fb7185",
          borderDash: [4, 4],
          borderWidth: 2,
          tension: 0.3,
          pointRadius: 0,
          fill: false,
        },
        {
          label: "Wind Available (kW)",
          data: [],
          borderColor: "#06b6d4",
          backgroundColor: "rgba(6, 182, 212, 0.15)",
          borderWidth: 1.5,
          tension: 0.3,
          pointRadius: 0,
          fill: true,
        },
        {
          label: "Solar Available (kW)",
          data: [],
          borderColor: "#fbbf24",
          backgroundColor: "rgba(251, 191, 36, 0.12)",
          borderWidth: 1.5,
          tension: 0.3,
          pointRadius: 0,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: {
            color: "#94a3b8",
            boxWidth: 10,
            font: { size: 9, family: "JetBrains Mono" },
          },
        },
        tooltip: {
          backgroundColor: "rgba(15, 23, 42, 0.95)",
          titleFont: { size: 11, family: "JetBrains Mono" },
          bodyFont: { size: 10, family: "JetBrains Mono" },
          borderColor: "rgba(56, 189, 248, 0.3)",
          borderWidth: 1,
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(51, 65, 85, 0.25)" },
          ticks: { color: "#64748b", font: { size: 9, family: "JetBrains Mono" } },
        },
        y: {
          grid: { color: "rgba(51, 65, 85, 0.25)" },
          ticks: {
            color: "#64748b",
            font: { size: 9, family: "JetBrains Mono" },
            callback: (v) => `${v}kW`,
          },
        },
      },
    },
  });
}

function updateForecastChart(forecast) {
  if (!forecastChartInstance || !forecast) return;
  forecastChartInstance.data.labels = forecast.hours || [];
  forecastChartInstance.data.datasets[0].data = forecast.electrical_kwe || [];
  forecastChartInstance.data.datasets[1].data = forecast.thermal_kwth || [];
  forecastChartInstance.data.datasets[2].data = forecast.wind_available_kw || [];
  forecastChartInstance.data.datasets[3].data = forecast.solar_available_kw || [];
  forecastChartInstance.update("none"); // Update smoothly without glitch
}

function initDispatchDonutChart() {
  const donutEl = document.getElementById("dispatch-donut-chart");
  if (!donutEl) return;

  dispatchDonutInstance = new Chart(donutEl, {
    type: "doughnut",
    data: {
      labels: ["Wind", "Solar", "Battery", "Diesel"],
      datasets: [
        {
          data: [40, 20, 15, 25],
          backgroundColor: ["#38bdf8", "#fbbf24", "#34d399", "#f43f5e"],
          borderColor: "rgba(15, 23, 42, 0.8)",
          borderWidth: 2,
          hoverOffset: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "74%",
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(15, 23, 42, 0.95)",
          bodyFont: { size: 10, family: "JetBrains Mono" },
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${ctx.raw}%`,
          },
        },
      },
    },
  });
}

function updateDispatchDonut(split) {
  if (!dispatchDonutInstance || !split) return;
  dispatchDonutInstance.data.datasets[0].data = [
    split.wind_pct || 0,
    split.solar_pct || 0,
    split.battery_pct || 0,
    split.diesel_pct || 0,
  ];
  dispatchDonutInstance.update("none");

  // Update text percentages
  document.getElementById("split-wind-pct").textContent = `${split.wind_pct}%`;
  document.getElementById("split-solar-pct").textContent = `${split.solar_pct}%`;
  document.getElementById("split-batt-pct").textContent = `${split.battery_pct}%`;
  document.getElementById("split-diesel-pct").textContent = `${split.diesel_pct}%`;

  const greenPct = Math.round((split.wind_pct || 0) + (split.solar_pct || 0));
  const ratioBadge = document.getElementById("green-energy-ratio");
  if (ratioBadge) {
    ratioBadge.textContent = `${greenPct}% RENEWABLE`;
    ratioBadge.className = `text-xs font-mono font-bold ${greenPct >= 50 ? "text-emerald-400" : "text-amber-400"}`;
  }
}

// -------------------------------------------------------------
// Terminal Logging Feed
// -------------------------------------------------------------
const terminalFeed = document.getElementById("terminal-feed");

function appendLog(category, badgeClass, message) {
  if (!terminalFeed) return;
  const timeStr = new Date().toTimeString().split(" ")[0];
  const div = document.createElement("div");
  div.className = "flex items-start gap-2 leading-relaxed animate-fadeIn";
  div.innerHTML = `
    <span class="text-slate-500 font-mono select-none">${timeStr}</span>
    <span class="px-1.5 py-0.2 rounded text-[9px] font-bold font-mono uppercase tracking-wider ${badgeClass}">${category}</span>
    <span class="text-slate-300 flex-1 font-mono">${message}</span>
  `;
  terminalFeed.appendChild(div);

  // Keep max 60 log lines
  while (terminalFeed.childNodes.length > 60) {
    terminalFeed.removeChild(terminalFeed.firstChild);
  }
  terminalFeed.scrollTop = terminalFeed.scrollHeight;
}

// -------------------------------------------------------------
// Telemetry UI Updates
// -------------------------------------------------------------
let lastGuardrailCount = 0;

function updateDashboardUI(data) {
  state.latestData = data;
  const telem = data.telemetry || {};
  const disp = data.dispatch || {};
  const guard = data.guardrail || {};
  const health = data.hardware_health || {};

  // 1. Top HUD Cards
  document.getElementById("hud-wind-speed").textContent = telem.wind_speed_ms?.toFixed(1) || "--";
  document.getElementById("hud-wind-gust").textContent = `${telem.wind_gust_ms?.toFixed(1) || "--"} m/s`;
  
  const windSpeed = telem.wind_speed_ms || 0;
  const windStateEl = document.getElementById("hud-wind-state");
  if (windSpeed > 25.0) {
    windStateEl.textContent = "GALE CUTOUT";
    windStateEl.className = "text-rose-400 text-[10px] uppercase font-bold animate-pulse";
  } else if (windSpeed >= 12.0) {
    windStateEl.textContent = "RATED MAX";
    windStateEl.className = "text-emerald-400 text-[10px] uppercase font-bold";
  } else if (windSpeed < 3.2) {
    windStateEl.textContent = "CUT-IN IDLE";
    windStateEl.className = "text-slate-400 text-[10px] uppercase font-bold";
  } else {
    windStateEl.textContent = "GENERATING";
    windStateEl.className = "text-cyan-400 text-[10px] uppercase font-bold";
  }

  // Temperature & Windchill
  document.getElementById("hud-temp").textContent = telem.ambient_temp_c?.toFixed(1) || "--";
  const t = telem.ambient_temp_c || -20;
  const v = Math.max(1.0, telem.wind_speed_ms || 10) * 3.6; // km/h
  const windChill = Math.round(13.12 + 0.6215 * t - 11.37 * Math.pow(v, 0.16) + 0.3965 * t * Math.pow(v, 0.16));
  document.getElementById("hud-windchill").textContent = `${windChill}°C`;

  // Solar Irradiance
  document.getElementById("hud-solar").textContent = Math.round(telem.solar_irradiance_wm2 || 0);

  // Battery SoC & Temp
  document.getElementById("hud-battery-soc").textContent = `${Math.round(telem.battery_soc_pct || 0)}%`;
  document.getElementById("hud-battery-temp").textContent = `${telem.battery_temp_c?.toFixed(1) || "--"}°C`;
  const derateFactor = Math.round((disp.battery_derating_factor || 1.0) * 100);
  document.getElementById("hud-battery-derate").textContent = `Derating: ${derateFactor}%`;

  const battBadge = document.getElementById("hud-battery-badge");
  if (telem.battery_temp_c <= -35.0 || telem.battery_soc_pct <= 20) {
    battBadge.textContent = "LOCKOUT";
    battBadge.className = "text-rose-400 text-[10px] font-bold uppercase animate-pulse";
  } else if (derateFactor < 100) {
    battBadge.textContent = "DERATED";
    battBadge.className = "text-amber-400 text-[10px] font-bold uppercase";
  } else {
    battBadge.textContent = "OPTIMAL";
    battBadge.className = "text-emerald-400 text-[10px] font-bold uppercase";
  }

  // Cumulative Diesel Fuel Saved
  document.getElementById("hud-diesel-saved").textContent = Math.round(disp.cumulative_diesel_saved_liters || 4280).toLocaleString();
  document.getElementById("hud-co2-saved").textContent = `${((disp.cumulative_co2_avoided_kg || 11400) / 1000).toFixed(1)} t`;

  // 2. Matrix Real-Time Readouts
  document.getElementById("matrix-elec-load").textContent = `${telem.station_load_kwe?.toFixed(1) || "--"} kWe`;
  document.getElementById("matrix-thermal-load").textContent = `${telem.thermal_load_kwth?.toFixed(1) || "--"} kWth`;
  document.getElementById("flow-wind-val").textContent = `${disp.p_wind_kw?.toFixed(1) || 0} kW`;
  document.getElementById("flow-solar-val").textContent = `${disp.p_solar_kw?.toFixed(1) || 0} kW`;
  document.getElementById("flow-battery-val").textContent = `${disp.p_battery_discharge_kw?.toFixed(1) || 0} kW`;
  document.getElementById("flow-diesel-val").textContent = `${((disp.p_diesel_1_kw || 0) + (disp.p_diesel_2_kw || 0)).toFixed(1)} kW`;

  // 3. Hardware Diagnostics
  const g1El = document.getElementById("diag-gen1-status");
  const g1Bar = document.getElementById("diag-gen1-bar");
  if (health.genset_1_status === "FAULT_TRIPPED") {
    g1El.textContent = "TRIPPED FAULT (0%)";
    g1El.className = "text-rose-400 font-bold animate-pulse";
    g1Bar.style.width = "0%";
    g1Bar.className = "bg-rose-500 h-1.5 rounded-full";
  } else {
    g1El.textContent = `RUNNING (${health.genset_1_health_pct}%)`;
    g1El.className = "text-emerald-400 font-bold";
    g1Bar.style.width = `${health.genset_1_health_pct}%`;
    g1Bar.className = "bg-emerald-500 h-1.5 rounded-full";
  }
  document.getElementById("diag-gen1-sub").textContent = `Run: ${guard.gen1_runtime_minutes || 35}m / 60m min-runtime`;

  // BESS Jacket
  const bessEl = document.getElementById("diag-bess-status");
  const bessBar = document.getElementById("diag-bess-bar");
  if (health.bess_status === "HEATER_FAULT") {
    bessEl.textContent = "HEATER FAULT (42%)";
    bessEl.className = "text-amber-400 font-bold animate-pulse";
    bessBar.style.width = "42%";
    bessBar.className = "bg-amber-500 h-1.5 rounded-full";
  } else {
    bessEl.textContent = `ACTIVE (${health.bess_thermal_health_pct}%)`;
    bessEl.className = "text-emerald-400 font-bold";
    bessBar.style.width = `${health.bess_thermal_health_pct}%`;
    bessBar.className = "bg-emerald-500 h-1.5 rounded-full";
  }
  document.getElementById("diag-bess-sub").textContent = `Core Temp: ${telem.battery_temp_c?.toFixed(1)}°C`;

  // System Status Pill Badge
  const statusBadge = document.getElementById("system-status-badge");
  const statusText = document.getElementById("system-status-text");
  if (guard.is_overridden) {
    statusBadge.className = "flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-950/70 border border-rose-500/50 text-rose-300 text-xs font-mono font-medium";
    statusText.textContent = "GUARDRAIL OVERRIDE ACTIVE";
  } else {
    statusBadge.className = "flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 text-xs font-mono font-medium";
    statusText.textContent = "MICROGRID LOCKED";
  }

  // SCADA Stream Live Telemetry Header
  const scadaBadge = document.getElementById("scada-stream-badge");
  const scadaText = document.getElementById("scada-stream-text");
  const scadaIcon = document.getElementById("scada-indicator-icon");
  if (scadaBadge && scadaText && scadaIcon) {
    if (telem.mode === "SCADA_MODE" && telem.scada_diagnostics) {
      const diag = telem.scada_diagnostics;
      scadaBadge.className = "flex items-center gap-2 px-2.5 py-1 rounded-lg bg-amber-950/70 border border-amber-500/50 text-amber-300 text-[11px] font-mono shadow-sm";
      scadaIcon.className = "fa-solid fa-server text-amber-400 animate-pulse";
      scadaText.textContent = `MODBUS 502 // #${diag.packet_sequence || 10420} // ${diag.latency_ms || 9.2}ms // ${diag.bus_frequency_hz || 50.0}Hz`;
    } else {
      scadaBadge.className = "hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-lg bg-slate-900/90 border border-slate-700 text-[11px] font-mono text-slate-400";
      scadaIcon.className = "fa-solid fa-satellite text-emerald-400";
      scadaText.textContent = "API: OPEN-METEO LIVE";
    }
  }

  // 4. Update Particle Matrix Density
  updateParticlePipes(disp);

  // 5. Update Donut Dispatch
  updateDispatchDonut(disp.dispatch_split);

  // 6. Update Forecast Graph (only auto-update if 24 Hours is selected)
  if (state.selectedHorizon === "24 Hours" && data.forecast_24h) {
    updateForecastChart(data.forecast_24h);
  }

  // 7. Update AI 1-Sentence Explanation
  if (data.explanation) {
    document.getElementById("ai-current-explanation-text").textContent = data.explanation;
  }

  // 8. Log Events to Terminal
  if (guard.is_overridden && guard.interventions?.length > 0) {
    guard.interventions.forEach((inv) => {
      appendLog("GUARDRAIL", "bg-rose-900/80 text-rose-300 border border-rose-600", `${inv.title}: ${inv.reason} (clamped to ${inv.clamped_val})`);
    });
  } else if (Math.random() < 0.15) {
    // Periodic telemetry log
    appendLog("OPTIMIZER", "bg-cyan-950 text-cyan-400 border border-cyan-700", `SciPy LP solved: Dispatched ${disp.p_wind_kw}kW Wind, ${disp.p_solar_kw}kW Solar, ${disp.p_diesel_1_kw}kW Gen1. Burn: ${disp.fuel_rate_liters_per_hour} L/h.`);
  }
}

// -------------------------------------------------------------
// Forecast Horizon Fetcher
// -------------------------------------------------------------
async function fetchAndApplyForecast(horizon) {
  try {
    const res = await fetch(`/api/forecast?horizon=${encodeURIComponent(horizon)}`);
    if (res.ok) {
      const data = await res.json();
      updateForecastChart(data);
      const titleEl = document.getElementById("forecast-header-title");
      if (titleEl) titleEl.textContent = `${horizon} Predictive AI Forecast`;
      appendLog("FORECAST", "bg-cyan-950 text-cyan-300 border border-cyan-700", `Loaded LightGBM multi-step forecast for '${horizon}'.`);
    }
  } catch (e) {
    console.error("Forecast fetch error:", e);
  }
}

// -------------------------------------------------------------
// WebSocket Client
// -------------------------------------------------------------
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

  state.ws = new WebSocket(wsUrl);

  state.ws.onopen = () => {
    state.wsConnected = true;
    state.reconnectAttempts = 0;
    appendLog("SYSTEM", "bg-emerald-950 text-emerald-300 border border-emerald-700", "Telemetry WebSocket connected at 1-sec streaming rate.");
  };

  state.ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateDashboardUI(data);
    } catch (e) {
      console.error("Failed to parse telemetry packet:", e);
    }
  };

  state.ws.onclose = () => {
    state.wsConnected = false;
    const retryDelay = Math.min(5000, 1000 * Math.pow(1.5, state.reconnectAttempts));
    state.reconnectAttempts++;
    setTimeout(connectWebSocket, retryDelay);
  };

  state.ws.onerror = (err) => {
    console.warn("WebSocket error:", err);
  };
}

// -------------------------------------------------------------
// Station & Mode Switchers
// -------------------------------------------------------------
const btnMaitri = document.getElementById("btn-maitri");
const btnBharati = document.getElementById("btn-bharati");
const btnModeDemo = document.getElementById("btn-mode-demo");
const btnModeScada = document.getElementById("btn-mode-scada");
const stationNameEl = document.getElementById("active-station-name");

btnMaitri.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/station/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ station_id: "MAITRI" }),
    });
    if (res.ok) {
      state.stationId = "MAITRI";
      btnMaitri.className = "px-3 py-1 rounded text-xs font-semibold tracking-wider transition-all bg-cyan-500 text-slate-950 shadow-md";
      btnBharati.className = "px-3 py-1 rounded text-xs font-semibold tracking-wider transition-all text-slate-400 hover:text-white";
      stationNameEl.textContent = "Maitri Research Station (Queen Maud Land)";
      appendLog("STATION", "bg-blue-950 text-blue-300 border border-blue-600", "Switched active microgrid telemetry to Maitri Station (-70°45'S).");
    }
  } catch (e) {
    console.error(e);
  }
});

btnBharati.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/station/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ station_id: "BHARATI" }),
    });
    if (res.ok) {
      state.stationId = "BHARATI";
      btnBharati.className = "px-3 py-1 rounded text-xs font-semibold tracking-wider transition-all bg-cyan-500 text-slate-950 shadow-md";
      btnMaitri.className = "px-3 py-1 rounded text-xs font-semibold tracking-wider transition-all text-slate-400 hover:text-white";
      stationNameEl.textContent = "Bharati Research Station (Larsemann Hills)";
      appendLog("STATION", "bg-blue-950 text-blue-300 border border-blue-600", "Switched active microgrid telemetry to Bharati Station (-69°24'S).");
    }
  } catch (e) {
    console.error(e);
  }
});

btnModeDemo.addEventListener("click", async () => {
  try {
    await fetch("/api/mode/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "DEMO_MODE" }),
    });
    state.mode = "DEMO_MODE";
    btnModeDemo.className = "px-3 py-1 rounded text-xs font-semibold tracking-wider transition-all bg-emerald-500 text-slate-950 shadow-md";
    btnModeScada.className = "px-3 py-1 rounded text-xs font-semibold tracking-wider transition-all text-slate-400 hover:text-white";
    appendLog("MODE", "bg-emerald-950 text-emerald-300 border border-emerald-600", "Switched to DEMO_MODE (Live Open-Meteo Antarctic API).");
  } catch (e) {
    console.error(e);
  }
});

btnModeScada.addEventListener("click", async () => {
  try {
    await fetch("/api/mode/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "SCADA_MODE" }),
    });
    state.mode = "SCADA_MODE";
    btnModeScada.className = "px-3 py-1 rounded text-xs font-semibold tracking-wider transition-all bg-emerald-500 text-slate-950 shadow-md";
    btnModeDemo.className = "px-3 py-1 rounded text-xs font-semibold tracking-wider transition-all text-slate-400 hover:text-white";
    appendLog("MODE", "bg-amber-950 text-amber-300 border border-amber-600", "Switched to SCADA_MODE (Modbus TCP Registers 40001-40016).");
  } catch (e) {
    console.error(e);
  }
});

// -------------------------------------------------------------
// Commander Override Controls (Sliders & Fault Injections)
// -------------------------------------------------------------
const sliderTemp = document.getElementById("slider-temp");
const sliderTempVal = document.getElementById("slider-temp-val");
const sliderWind = document.getElementById("slider-wind");
const sliderWindVal = document.getElementById("slider-wind-val");
const btnTripGen1 = document.getElementById("btn-trip-gen1");
const btnFaultBess = document.getElementById("btn-fault-bess");
const btnResetOverrides = document.getElementById("btn-reset-overrides");

sliderTemp.addEventListener("input", (e) => {
  const val = parseFloat(e.target.value);
  sliderTempVal.textContent = `${val}°C`;
  sendOverrides({ ambient_temp_c: val });
});

sliderWind.addEventListener("input", (e) => {
  const val = parseFloat(e.target.value);
  sliderWindVal.textContent = `${val} m/s`;
  sendOverrides({ wind_speed_ms: val });
});

btnTripGen1.addEventListener("click", () => {
  state.tripGen1 = !state.tripGen1;
  btnTripGen1.className = state.tripGen1
    ? "px-2.5 py-1.5 rounded bg-rose-600 text-white text-[11px] font-mono font-medium transition-all flex items-center justify-center gap-1.5 shadow-lg shadow-rose-900/50"
    : "px-2.5 py-1.5 rounded bg-slate-900 hover:bg-rose-950/80 border border-slate-700 text-slate-300 text-[11px] font-mono font-medium transition-all flex items-center justify-center gap-1.5";
  sendOverrides({ fault_genset_1: state.tripGen1 });
  appendLog("COMMANDER", "bg-rose-950 text-rose-300 border border-rose-600", `Commander manually ${state.tripGen1 ? "TRIPPED" : "RESTORED"} Genset 1 breaker.`);
});

btnFaultBess.addEventListener("click", () => {
  state.faultBess = !state.faultBess;
  btnFaultBess.className = state.faultBess
    ? "px-2.5 py-1.5 rounded bg-amber-600 text-white text-[11px] font-mono font-medium transition-all flex items-center justify-center gap-1.5 shadow-lg shadow-amber-900/50"
    : "px-2.5 py-1.5 rounded bg-slate-900 hover:bg-amber-950/80 border border-slate-700 text-slate-300 text-[11px] font-mono font-medium transition-all flex items-center justify-center gap-1.5";
  sendOverrides({ fault_battery_heater: state.faultBess });
  appendLog("COMMANDER", "bg-amber-950 text-amber-300 border border-amber-600", `Commander simulated BESS thermal heating jacket failure.`);
});

btnResetOverrides.addEventListener("click", async () => {
  sliderTemp.value = -20;
  sliderTempVal.textContent = "Default";
  sliderWind.value = 10;
  sliderWindVal.textContent = "Default";
  state.tripGen1 = false;
  state.faultBess = false;
  btnTripGen1.className = "px-2.5 py-1.5 rounded bg-slate-900 hover:bg-rose-950/80 border border-slate-700 text-slate-300 text-[11px] font-mono font-medium transition-all flex items-center justify-center gap-1.5";
  btnFaultBess.className = "px-2.5 py-1.5 rounded bg-slate-900 hover:bg-amber-950/80 border border-slate-700 text-slate-300 text-[11px] font-mono font-medium transition-all flex items-center justify-center gap-1.5";
  try {
    await fetch("/api/commander/reset", { method: "POST" });
    appendLog("COMMANDER", "bg-slate-800 text-slate-300 border border-slate-600", "Commander overrides reset to nominal polar physics.");
  } catch (e) {
    console.error(e);
  }
});

async function sendOverrides(payload) {
  try {
    await fetch("/api/commander/override", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    console.error("Failed to send override:", e);
  }
}

// -------------------------------------------------------------
// Commander AI Assistant Chatbox Logic
// -------------------------------------------------------------
const btnOpenChat = document.getElementById("btn-open-chat");
const btnCloseChat = document.getElementById("btn-close-chat");
const chatDrawer = document.getElementById("chat-drawer");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");

btnOpenChat.addEventListener("click", () => {
  chatDrawer.classList.remove("hidden");
  chatInput.focus();
});

btnCloseChat.addEventListener("click", () => {
  chatDrawer.classList.add("hidden");
});

document.querySelectorAll(".quick-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    chatInput.value = chip.textContent.trim();
    chatForm.dispatchEvent(new Event("submit"));
  });
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = chatInput.value.trim();
  if (!query) return;

  // Append user message
  const userMsgEl = document.createElement("div");
  userMsgEl.className = "p-2.5 rounded-lg bg-cyan-950/50 border border-cyan-500/30 text-cyan-200 text-right font-sans";
  userMsgEl.innerHTML = `<strong class="text-cyan-400 block text-[10px] uppercase font-mono mb-0.5">Commander:</strong>${query}`;
  chatMessages.appendChild(userMsgEl);
  chatInput.value = "";
  chatMessages.scrollTop = chatMessages.scrollHeight;

  // Placeholder AI response loading
  const aiMsgEl = document.createElement("div");
  aiMsgEl.className = "p-2.5 rounded-lg bg-slate-900/90 border border-slate-800 text-slate-300 font-sans";
  aiMsgEl.innerHTML = `<strong class="text-cyan-400 block text-[10px] uppercase font-mono mb-0.5">PolarOPS Copilot:</strong><span class="italic text-slate-400 animate-pulse">Analyzing microgrid telemetry & LLM inference...</span>`;
  chatMessages.appendChild(aiMsgEl);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query }),
    });
    if (res.ok) {
      const data = await res.json();
      aiMsgEl.innerHTML = `<strong class="text-cyan-400 block text-[10px] uppercase font-mono mb-0.5">PolarOPS Copilot:</strong>${data.answer}`;
    } else {
      aiMsgEl.innerHTML = `<strong class="text-rose-400 block text-[10px] uppercase font-mono mb-0.5">Error:</strong>Unable to reach AI inference engine.`;
    }
  } catch (err) {
    aiMsgEl.innerHTML = `<strong class="text-rose-400 block text-[10px] uppercase font-mono mb-0.5">Error:</strong>Network error communicating with AI server.`;
  }
  chatMessages.scrollTop = chatMessages.scrollHeight;
});

// -------------------------------------------------------------
// UTC Antarctic Station Clock
// -------------------------------------------------------------
function updateUtcClock() {
  const clockEl = document.getElementById("utc-clock");
  if (clockEl) {
    const now = new Date();
    clockEl.textContent = `${now.toUTCString().slice(17, 25)} UTC`;
  }
}
setInterval(updateUtcClock, 1000);
updateUtcClock();

// -------------------------------------------------------------
// Initialization
// -------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
  initForecastChart();
  initDispatchDonutChart();
  connectWebSocket();

  // Bind Forecast Horizon Select Dropdown
  const horizonSelect = document.getElementById("forecast-horizon-select");
  if (horizonSelect) {
    horizonSelect.addEventListener("change", (e) => {
      state.selectedHorizon = e.target.value;
      fetchAndApplyForecast(state.selectedHorizon);
    });
  }

  appendLog("SYSTEM", "bg-cyan-950 text-cyan-300 border border-cyan-700", "PolarOPS SEMS Digital Twin booted. Standby for 1-second telemetry.");
});

