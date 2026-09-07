# PolarOPS: AI-Driven Smart Energy Management System (SEMS)
### Autonomous Microgrid & Digital Twin for Indian Polar Research Stations (Maitri & Bharati)

![PolarOPS Architecture](https://img.shields.io/badge/System-PolarOPS%20SEMS-06b6d4?style=for-the-badge)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi)
![SciPy LP](https://img.shields.io/badge/MPC-SciPy%20Linprog-blue?style=for-the-badge)
![LightGBM](https://img.shields.io/badge/Forecasting-LightGBM-brightgreen?style=for-the-badge)
![Groq](https://img.shields.io/badge/AI-Groq%20Llama--3-f59e0b?style=for-the-badge)

PolarOPS is an end-to-end production-ready, full-stack web application for an **AI-Driven Smart Energy Management System (SEMS)** designed specifically for the extreme conditions of Indian Antarctic research stations (**Maitri** in Schirmacher Oasis and **Bharati** in Larsemann Hills).

---

## ❄️ Key Features & Engineering Highlights

1. **Digital Twin Dual-Mode Architecture**:
   - `DEMO_MODE`: Ingests live Antarctic weather via Open-Meteo API using exact GPS coordinates for Maitri (`-70.7661°S, 11.7358°E`) and Bharati (`-69.4078°S, 76.1872°E`), with realistic diurnal physics and snow albedo reflection gain.
   - `SCADA_MODE`: Ingests emulated industrial Modbus TCP / MQTT registers (40001-40016: RPM, bus frequency 50Hz, 3-phase voltage, oil pressure, CHP loop temperature).

2. **Predictive AI Demand & Weather Forecaster (LightGBM)**:
   - Forecasts 24 hours of Electrical Load ($P_{\text{load}, e}$) and Thermal Heating Demand ($Q_{\text{load}, th}$).
   - Integrates aerodynamic wind turbine cut-in, rated, and cut-out curves with bifacial solar albedo gains (+20%).

3. **Model Predictive Control (MPC via SciPy Linear Programming)**:
   - Minimizes costly Arctic diesel fuel consumption while balancing Wind, Bifacial Solar, and Battery Energy Storage (BESS).
   - **Combined Heat & Power (CHP)**: Recovers 1.2 kWth waste heat per kWe of diesel generator power to supply station habitability heating.
   - **Temperature-Dependent Battery Derating**: Derates effective battery capacity below $-20^\circ\text{C}$ and enforces emergency lockout below $-35^\circ\text{C}$.

4. **Deterministic Safety Guardrail Layer**:
   - **60-Minute Minimum Run-Time**: Prevents diesel generator short-cycling, wet stacking, and cylinder thermal shock.
   - **Sub-Zero Battery Lockout**: Inhibits battery discharge if core temperature drops below $-35^\circ\text{C}$ or $\text{SoC} \le 20\%$.
   - **Storm Cutout Feathering**: Disengages wind turbines and deploys mechanical brakes if wind exceeds $25\text{ m/s}$.
   - **Blackout Defense**: Automatically spins up standby Genset 2 if spinning reserve drops below 15 kW headroom.

5. **Groq LLM Contextual Decision Engine**:
   - Generates 1-sentence plain-English explanations for every dispatch action and guardrail override.
   - **Commander AI Assistant**: Interactive Q&A chatbox answering operational questions (*"Why is Diesel running?"*, *"Can we sustain an 8-hour blizzard?"*) with full telemetry context.
   - *Offline Resilience*: If no `GROQ_API_KEY` is provided, an intelligent built-in polar expert heuristic fallback guarantees 100% functionality during offline hackathon demos.

6. **Offline Batch SQLite Logging (`sems_logs.db`)**:
   - Automatically logs all 1-second telemetry ticks, optimizer decisions, guardrail safety interventions, and AI explanations.

7. **Futuristic Glassmorphism Commander Dashboard**:
   - Dark, immersive polar aesthetic with full-screen windmill video background.
   - **Energy Flow Matrix**: Dynamic HTML5 canvas rendering glowing particle vectors between Wind, Solar, BESS, Diesel, and Station loads.
   - **Interactive Commander Override Sliders**: Inject $-40^\circ\text{C}$ Blizzard, Gale Winds, or trip Genset 1 to observe instant real-time recalculation!

---

## 📁 Folder Structure

```
PolarOPS/
├── .env                             # Environment variables & API keys
├── .env.example                     # Sample configuration
├── requirements.txt                 # Python dependencies
├── README.md                        # Documentation & setup guide
├── sems_logs.db                     # Local SQLite database (auto-generated)
├── backend/
│   ├── __init__.py
│   ├── config.py                    # Station hardware specs, CHP constants, derating limits
│   ├── data_ingestion.py            # Unified ingestion abstraction (Open-Meteo vs SCADA)
│   ├── ai_models.py                 # LightGBM 24-hr electrical & thermal demand forecast
│   ├── optimizer.py                 # SciPy LP (linprog) MPC fuel minimizer
│   ├── guardrail.py                 # Deterministic safety rule engine (60-min runtime, freeze lockout)
│   ├── logger.py                    # SQLite persistence logger for audit trail
│   ├── llm_service.py               # Groq LLM integration & offline fallback
│   └── main.py                      # FastAPI app, 1-sec WebSocket broadcaster & REST API
├── frontend/
│   ├── index.html                   # Commander Glassmorphism Dashboard
│   ├── styles.css                   # Glassmorphism, animations, glow utilities
│   └── app.js                       # WebSockets, Canvas Energy Matrix, Chart.js, AI Chat
└── scratch/
    └── test_pipeline.py             # End-to-end smoke test suite
```

---

## 🚀 Quick Start Instructions

### 1. Prerequisites
- Python 3.10+ installed
- Modern web browser (Chrome, Edge, Firefox, Brave)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. (Optional) Configure Groq API Key
Open `.env` and replace with your Groq API key:
```env
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
```
*(Note: If you do not have a Groq key, leave it as default. The system automatically switches to its offline expert engine so everything runs smoothly!)*

### 4. Run Smoke Test Suite
```bash
python scratch/test_pipeline.py
```

### 5. Launch the PolarOPS Server
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Open the Dashboard
Navigate to:
```
http://localhost:8000
```

---

## 🎮 Commander Live Demo Playbook

1. **Switch Stations**:
   - Click **BHARATI** or **MAITRI** in the top bar to toggle between coastal and inland Antarctic stations. Notice base loads and renewable capacities adapt.
2. **Toggle Modes**:
   - Click **SCADA_BUS** to inspect emulated Modbus TCP registers (40001-40016), or click **DEMO_API** for live Open-Meteo weather data.
3. **Trigger -40°C Blizzard**:
   - In the **Commander Override Controls** (bottom right), drag the **Ambient Temp** slider to `-40°C`.
   - Observe the immediate spike in station thermal demand ($Q_{\text{load}, th}$), BESS temperature derating, and CHP diesel modulation.
4. **Trigger Gale Storm Cutout**:
   - Drag the **Wind Velocity** slider above `25 m/s`.
   - Watch the Safety Guardrail instantly trip: the wind array is feathered, mechanical brakes engage ($P_{\text{wind}} = 0$), and spinning reserve is brought online with an audit log explanation.
5. **Trip Genset 1**:
   - Click **Trip Genset 1**. Watch Standby Genset 2 spin up within seconds to prevent microgrid blackout.
6. **Ask Commander AI Copilot**:
   - Click the floating **Ask Station AI Assistant** button.
   - Click any chip or ask: *"Why did we turn on Diesel 2?"* or *"What is our battery health?"* to receive context-aware engineering answers.
