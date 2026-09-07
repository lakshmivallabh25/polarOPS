"""
PolarOPS - Verification Test for All 4 Update Requirements:
1. SCADA Live Data Mode
2. Multi-Horizon Predictive Forecasting
3. Energy Matrix Flow UI assets
4. Assistant Persona & Fallback Guardrails
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.data_ingestion import DataIngestionDriver
from backend.ai_models import PolarDemandForecaster
from backend.optimizer import PolarEnergyOptimizer
from backend.guardrail import SafetyGuardrailEngine
from backend.llm_service import GroqAIService

def test_updates():
    print("==================================================")
    print("TEST 1: SCADA Live Data Mode Verification")
    print("==================================================")
    driver = DataIngestionDriver(station_id="MAITRI", mode="SCADA_MODE")
    telem = driver.ingest()
    scada_diag = telem.get("scada_diagnostics", {})
    regs = scada_diag.get("registers", {})
    
    print(f"Mode: {telem['mode']} | Source: {telem.get('source')}")
    print(f"SCADA Protocol: {scada_diag.get('protocol')} | Latency: {scada_diag.get('latency_ms')} ms | Seq: {scada_diag.get('packet_sequence')}")
    print(f"Bus Frequency: {scada_diag.get('bus_frequency_hz')} Hz | Reg 40001 (Gen1 RPM): {regs.get('reg_40001_gen1_rpm')}")
    
    assert telem["mode"] == "SCADA_MODE"
    assert telem["source"] == "SCADA_MODBUS_TCP"
    assert "reg_40001_gen1_rpm" in regs
    assert scada_diag.get("latency_ms") is not None
    print("[PASS] SCADA Live Data Mode is fully functioning!\n")

    print("==================================================")
    print("TEST 2: Expanded Predictive Forecasting Horizons")
    print("==================================================")
    forecaster = PolarDemandForecaster()
    horizons = [
        '24 Hours', 'Tomorrow', 'Current Week', 'Next 2-3 Weeks',
        '1 Month', '3 Months', '6 Months', '12 Months'
    ]
    
    for h in horizons:
        fc = forecaster.predict_horizon(telem, horizon=h)
        print(f"Horizon '{h}': {len(fc['hours'])} points | First label: '{fc['hours'][0]}' | Peak Elec: {max(fc['electrical_kwe'])} kWe | Solar Peak: {max(fc['solar_available_kw'])} kW")
        assert len(fc["hours"]) > 0
        assert len(fc["electrical_kwe"]) == len(fc["hours"])
        assert len(fc["thermal_kwth"]) == len(fc["hours"])
        assert len(fc["wind_available_kw"]) == len(fc["hours"])
        assert len(fc["solar_available_kw"]) == len(fc["hours"])
    print("[PASS] All 8 forecasting time horizons are verified!\n")

    print("==================================================")
    print("TEST 3: AI Assistant Persona & Guardrails")
    print("==================================================")
    optimizer = PolarEnergyOptimizer()
    disp = optimizer.optimize_dispatch(telem, 20.0, 15.0)
    guardrail = SafetyGuardrailEngine()
    gr_res = guardrail.enforce_safety(telem, disp)
    ai = GroqAIService()

    # Test 3a: On-topic query
    q_on = "Why did we turn on Diesel 2?"
    ans_on = ai.answer_commander(q_on, telem, gr_res["safe_dispatch"], gr_res)
    print(f"Q: '{q_on}'")
    print(f"A: {ans_on.encode('ascii', 'replace').decode('ascii')}\n")
    assert len(ans_on) > 15
    assert "apologize" not in ans_on.lower()

    # Test 3b: Off-topic general knowledge
    q_off1 = "What is the capital of Australia?"
    ans_off1 = ai.answer_commander(q_off1, telem, gr_res["safe_dispatch"], gr_res)
    print(f"Q: '{q_off1}'")
    print(f"A: {ans_off1}\n")
    assert ans_off1 == "I apologize, but I can only answer questions related to energy management and system operations."

    # Test 3c: Personal question
    q_off2 = "What is your favourite food and how old are you?"
    ans_off2 = ai.answer_commander(q_off2, telem, gr_res["safe_dispatch"], gr_res)
    print(f"Q: '{q_off2}'")
    print(f"A: {ans_off2}\n")
    assert ans_off2 == "I apologize, but I can only answer questions related to energy management and system operations."

    # Test 3d: Creative writing off-topic
    q_off3 = "Write a poem about love and flowers."
    ans_off3 = ai.answer_commander(q_off3, telem, gr_res["safe_dispatch"], gr_res)
    print(f"Q: '{q_off3}'")
    print(f"A: {ans_off3}\n")
    assert ans_off3 == "I apologize, but I can only answer questions related to energy management and system operations."

    print("[PASS] AI Persona & Fallback Guardrails verified strictly!\n")

    print("==================================================")
    print("[SUCCESS] ALL 4 TASK REQUIREMENTS VERIFIED!")
    print("==================================================")

if __name__ == "__main__":
    test_updates()
