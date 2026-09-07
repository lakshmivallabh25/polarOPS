"""
PolarOPS - End-to-End Pipeline Smoke Test
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.config import STATIONS
from backend.data_ingestion import DataIngestionDriver
from backend.ai_models import PolarDemandForecaster
from backend.optimizer import PolarEnergyOptimizer
from backend.guardrail import SafetyGuardrailEngine
from backend.logger import SystemEventLogger
from backend.llm_service import GroqAIService

def test_full_pipeline():
    print(">>> 1. Testing Data Ingestion...")
    driver = DataIngestionDriver(station_id="MAITRI", mode="DEMO_MODE")
    telemetry = driver.ingest()
    print(f"    Telemetry: Station={telemetry['station_id']}, Temp={telemetry['ambient_temp_c']}°C, Wind={telemetry['wind_speed_ms']}m/s, Load={telemetry['station_load_kwe']}kWe")
    assert telemetry['station_id'] == "MAITRI"
    
    print(">>> 2. Testing LightGBM 24h Forecaster...")
    forecaster = PolarDemandForecaster()
    forecast = forecaster.predict_24h(telemetry)
    print(f"    Forecast: 24 points generated. Peak Electrical = {max(forecast['electrical_kwe'])} kWe, Peak Thermal = {max(forecast['thermal_kwth'])} kWth")
    assert len(forecast['hours']) == 24
    
    print(">>> 3. Testing SciPy LP Optimizer (MPC)...")
    optimizer = PolarEnergyOptimizer()
    wind_kw = forecaster.calculate_wind_power(telemetry['wind_speed_ms'], 120.0)
    solar_kw = forecaster.calculate_solar_power(telemetry['solar_irradiance_wm2'], 75.0)
    dispatch = optimizer.optimize_dispatch(telemetry, wind_kw, solar_kw)
    print(f"    Dispatch: Gen1={dispatch['p_diesel_1_kw']}kW, Gen2={dispatch['p_diesel_2_kw']}kW, Wind={dispatch['p_wind_kw']}kW, Solar={dispatch['p_solar_kw']}kW, BESS={dispatch['p_battery_discharge_kw']}kW")
    print(f"    CHP Thermal Recovered={dispatch['q_chp_thermal_kwth']}kWth, Aux Thermal={dispatch['q_aux_thermal_kwth']}kWth")
    assert "p_diesel_1_kw" in dispatch
    
    print(">>> 4. Testing Safety Guardrail Engine...")
    guardrail = SafetyGuardrailEngine()
    # Test min runtime clamp
    gr_res = guardrail.enforce_safety(telemetry, dispatch)
    print(f"    Guardrail Active: {gr_res['is_overridden']}, Interventions={len(gr_res['interventions'])}")
    if gr_res['interventions']:
        print(f"    Triggered: {gr_res['interventions'][0]['title']}")
        
    print(">>> 5. Testing Sub-zero Battery Freeze Guardrail...")
    cold_telemetry = dict(telemetry)
    cold_telemetry['battery_temp_c'] = -38.0
    cold_telemetry['battery_soc_pct'] = 80.0
    opt_cold = dict(dispatch)
    opt_cold['p_battery_discharge_kw'] = 45.0
    cold_res = guardrail.enforce_safety(cold_telemetry, opt_cold)
    print(f"    Sub-zero Lockout Triggered: {cold_res['is_overridden']}, Batt Setpoint={cold_res['safe_dispatch']['p_battery_discharge_kw']}kW")
    assert cold_res['safe_dispatch']['p_battery_discharge_kw'] == 0.0
    
    print(">>> 6. Testing Groq / Fallback AI Service...")
    ai = GroqAIService()
    explanation = ai.explain_dispatch(telemetry, gr_res['safe_dispatch'], gr_res)
    print(f"    AI 1-Sentence Explanation: {explanation}")
    assert len(explanation) > 10
    
    chat_answer = ai.answer_commander("Why did we turn on Diesel 2?", telemetry, gr_res['safe_dispatch'], gr_res)
    print(f"    AI Commander Chat: {chat_answer}")
    assert len(chat_answer) > 15
    
    print(">>> 7. Testing SQLite Persistent Logger...")
    logger = SystemEventLogger()
    logger.log_telemetry_and_dispatch(telemetry, gr_res['safe_dispatch'], gr_res, explanation)
    hist = logger.get_recent_history(limit=5)
    print(f"    SQLite Logs: {len(hist['telemetry'])} telemetry rows, {len(hist['ai_explanations'])} AI rows")
    assert len(hist['telemetry']) > 0

    print("\n[SUCCESS] ALL PIPELINE TESTS PASSED!")

if __name__ == "__main__":
    test_full_pipeline()
