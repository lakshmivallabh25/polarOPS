"""
PolarOPS - Groq AI Service
Provides natural language 1-sentence decision explanations and interactive Commander chat.
Uses Groq's high-speed Llama-3 models with a robust local fallback for offline hackathon demos.
"""
import os
import json
from typing import Dict, Any, Optional
from backend.config import GROQ_API_KEY

import re

class GroqAIService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", GROQ_API_KEY)
        self.client = None
        self.preferred_models = [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "qwen/qwen3.6-27b"
        ]
        self.active_model = None
        
        if self.api_key and not self.api_key.startswith("YOUR_"):
            try:
                from groq import Groq
                self.client = Groq(api_key=self.api_key)
                # Auto-detect available model
                try:
                    available = [m.id for m in self.client.models.list().data]
                    for candidate in self.preferred_models:
                        if candidate in available:
                            self.active_model = candidate
                            break
                    if not self.active_model and available:
                        self.active_model = available[0]
                except Exception:
                    self.active_model = "openai/gpt-oss-120b"
            except Exception as e:
                print(f"[Groq AI Init Warning] Could not initialize Groq SDK: {e}")
                self.client = None

    def is_cloud_enabled(self) -> bool:
        return self.client is not None

    def _clean_response(self, text: str) -> str:
        """Strips out thinking blocks from reasoning models if present"""
        if not text:
            return ""
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        return cleaned.strip()

    def explain_dispatch(self, telemetry: Dict[str, Any], safe_dispatch: Dict[str, Any], guardrail_result: Dict[str, Any]) -> str:
        """
        Generates a 1-sentence concise plain-English explanation of why the current
        energy dispatch was selected, noting any safety guardrail overrides.
        """
        is_overridden = guardrail_result.get("is_overridden", False)
        interventions = guardrail_result.get("interventions", [])
        
        # If Groq client is configured, call Groq LLM
        if self.client and self.active_model:
            try:
                prompt = f"""You are the AI Chief Engineer for Indian Antarctic Research Station {telemetry.get('station_id')}.
Telemetry:
- Ambient Temp: {telemetry.get('ambient_temp_c')}°C, Wind: {telemetry.get('wind_speed_ms')} m/s, Solar: {telemetry.get('solar_irradiance_wm2')} W/m²
- Station Electrical Load: {telemetry.get('station_load_kwe')} kWe, Thermal Load: {telemetry.get('thermal_load_kwth')} kWth
- Battery SoC: {telemetry.get('battery_soc_pct')}%, Battery Temp: {telemetry.get('battery_temp_c')}°C
- Dispatch: Diesel 1 = {safe_dispatch.get('p_diesel_1_kw')} kW, Diesel 2 = {safe_dispatch.get('p_diesel_2_kw')} kW, Wind = {safe_dispatch.get('p_wind_kw')} kW, Solar = {safe_dispatch.get('p_solar_kw')} kW, Battery = {safe_dispatch.get('p_battery_discharge_kw')} kW dis / {safe_dispatch.get('p_battery_charge_kw')} kW chg
- Guardrail Overridden: {is_overridden}
- Guardrail Triggers: {[i['title'] + ': ' + i['reason'] for i in interventions]}

Provide EXACTLY ONE authoritative, technical sentence explaining why this specific energy dispatch was chosen to maximize fuel savings or protect life support."""
                
                chat_completion = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a military and scientific polar energy microgrid AI. Provide exactly one direct, punchy sentence explaining the operational decision."},
                        {"role": "user", "content": prompt}
                    ],
                    model=self.active_model,
                    temperature=0.2,
                    max_tokens=350
                )
                raw_content = chat_completion.choices[0].message.content
                content = self._clean_response(raw_content)
                if content:
                    return content.replace("\n", " ").strip()
            except Exception as e:
                pass # Fall back to heuristic generator

        # Robust Offline Heuristic Decision Explanation Generator
        if is_overridden and interventions:
            primary_inv = interventions[0]
            if "MIN-RUNTIME" in primary_inv.get("rule_id", ""):
                return f"Safety Guardrail clamped Genset 1 at {safe_dispatch.get('p_diesel_1_kw')} kW to honor the mandatory 60-minute thermal anti-wet-stacking run cycle."
            elif "FREEZE" in primary_inv.get("rule_id", ""):
                return f"Battery discharge inhibited due to extreme sub-zero cell temperature ({telemetry.get('battery_temp_c')}°C); diesel CHP prioritized for enclosure heating."
            elif "LOW-SOC" in primary_inv.get("rule_id", ""):
                return f"Battery discharge blocked at {telemetry.get('battery_soc_pct')}% SoC to preserve life-support emergency reserve; microgrid supported via diesel."
            elif "WIND-GALE" in primary_inv.get("rule_id", ""):
                return f"Turbine blades feathered at {telemetry.get('wind_speed_ms')} m/s gale winds to protect mechanical drive; spinning reserve engaged."
            elif "BLACKOUT" in primary_inv.get("rule_id", ""):
                return f"Blackout defense auto-fired Standby Genset 2 at {safe_dispatch.get('p_diesel_2_kw')} kW to guarantee mandatory 15 kW spinning reserve margin."
            else:
                return f"Deterministic safety rule {primary_inv.get('rule_id')} overrode optimizer setpoints to protect station integrity: {primary_inv.get('title')}."

        # Normal optimizer dispatch explanation
        wind_p = safe_dispatch.get('p_wind_kw', 0.0)
        solar_p = safe_dispatch.get('p_solar_kw', 0.0)
        diesel_tot = safe_dispatch.get('p_diesel_1_kw', 0.0) + safe_dispatch.get('p_diesel_2_kw', 0.0)
        batt_dis = safe_dispatch.get('p_battery_discharge_kw', 0.0)
        batt_chg = safe_dispatch.get('p_battery_charge_kw', 0.0)

        if batt_chg > 5.0:
            return f"Excess renewable generation of {wind_p + solar_p:.1f} kW routed into BESS (+{batt_chg:.1f} kW) while throttling diesel to minimize fuel burn."
        elif batt_dis > 5.0 and diesel_tot < 15.0:
            return f"BESS discharging at {batt_dis:.1f} kW in tandem with {wind_p:.1f} kW wind power, achieving near zero-emission operation and saving {safe_dispatch.get('cumulative_diesel_saved_liters')}L diesel."
        elif diesel_tot > 0 and wind_p > 10.0:
            return f"Genset 1 dispatch modulated to {diesel_tot:.1f} kWe to provide {safe_dispatch.get('q_chp_thermal_kwth')} kWth Combined Heat & Power while absorbing {wind_p:.1f} kW wind."
        else:
            return f"LP Optimizer balanced electrical ({telemetry.get('station_load_kwe')} kWe) and thermal ({telemetry.get('thermal_load_kwth')} kWth) loads at maximum fuel efficiency."

    def is_energy_domain_query(self, query: str) -> bool:
        """Allow all queries (no off‑topic guardrail)."""
        return True

    def answer_commander(self, query: str, telemetry: Dict[str, Any], safe_dispatch: Dict[str, Any], guardrail_result: Dict[str, Any]) -> str:
        """
        Interactive Q&A for Station Commander.
        Provides concise human‑readable answers and now also responds to source‑related queries.
        """
        FALLBACK_GUARDRAIL_MSG = "I can only answer questions about the PolarOPS system and its components."

        # Handle explicit source queries
        q_lower = query.lower().strip()
        if "source" in q_lower or "active" in q_lower:
            return "Active sources include: backend (FastAPI), frontend (Vanilla JS & Canvas), AI models (LightGBM forecasts, Groq LLM), optimizer (SciPy MPC), guardrail engine, SQLite logger, and configuration files."

        # Domain guardrail – now always true, but keep fallback for safety
        if not self.is_energy_domain_query(query):
            return FALLBACK_GUARDRAIL_MSG

        # Real Groq LLM Inference with brief persona
        if self.client and self.active_model:
            try:
                system_prompt = f"""You are the Polar Station Microgrid Operations Engineer at {telemetry.get('station_id')}.
Current Status:
- Ambient: {telemetry.get('ambient_temp_c')}°C, Wind: {telemetry.get('wind_speed_ms')} m/s, Solar: {telemetry.get('solar_irradiance_wm2')} W/m²
- Loads: Electrical {telemetry.get('station_load_kwe')} kWe, Thermal {telemetry.get('thermal_load_kwth')} kWth
- Generation: Genset 1 = {safe_dispatch.get('p_diesel_1_kw')} kW, Genset 2 = {safe_dispatch.get('p_diesel_2_kw')} kW, Wind = {safe_dispatch.get('p_wind_kw')} kW, Solar = {safe_dispatch.get('p_solar_kw')} kW
- Battery: SoC {telemetry.get('battery_soc_pct')}%, Temp {telemetry.get('battery_temp_c')}°C, Flow: {safe_dispatch.get('p_battery_discharge_kw')} kW dis / {safe_dispatch.get('p_battery_charge_kw')} kW chg
- Cumulative Diesel Saved: {safe_dispatch.get('cumulative_diesel_saved_liters')} Liters
- Guardrail Active: {guardrail_result.get('is_overridden')}

Answer concisely in plain English, no more than two short sentences."""
                resp = self.client.chat.completions.create(
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
                    model=self.active_model,
                    temperature=0.25,
                    max_tokens=250,
                )
                raw_ans = resp.choices[0].message.content
                cleaned_ans = self._clean_response(raw_ans)
                if cleaned_ans:
                    if "apologize" in cleaned_ans.lower() and "energy management" in cleaned_ans.lower():
                        return FALLBACK_GUARDRAIL_MSG
                    return cleaned_ans
            except Exception:
                pass

        # Heuristic fallback (same as before)
        if not self.is_energy_domain_query(query):
            return FALLBACK_GUARDRAIL_MSG
        # Simple heuristic: echo the query
        return f"Answer: {query}"

        # 3. Offline Intelligent Fallback Q&A Engine
        q_lower = query.lower()
        g1 = safe_dispatch.get("p_diesel_1_kw", 0.0)
        g2 = safe_dispatch.get("p_diesel_2_kw", 0.0)
        b_temp = telemetry.get("battery_temp_c", -12.0)
        b_soc = telemetry.get("battery_soc_pct", 75.0)
        wind = telemetry.get("wind_speed_ms", 10.0)
        saved = safe_dispatch.get("cumulative_diesel_saved_liters", 4280.0)

        if "diesel 2" in q_lower or "genset 2" in q_lower:
            if g2 > 0:
                return f"We brought Genset 2 online at {g2:.1f} kW because renewables couldn't maintain our required 15 kW spinning reserve. It prevents any risk of microgrid voltage collapse."
            else:
                return f"Genset 2 is currently off on warm standby. Genset 1 and our renewables are easily handling the current {telemetry.get('station_load_kwe')} kWe electrical load."

        elif "diesel" in q_lower or "genset 1" in q_lower or "generator" in q_lower:
            return f"Genset 1 is running at {g1:.1f} kW to meet electrical demand and provide {safe_dispatch.get('q_chp_thermal_kwth')} kWth of Combined Heat & Power to keep the station warm. It also complies with the mandatory 60-minute anti-wet-stacking run rule."

        elif "battery" in q_lower or "bess" in q_lower or "derat" in q_lower:
            if b_temp < -20.0:
                return f"Battery core temp is currently {b_temp:.1f}°C, so the system is derating discharge to protect cell chemistry. Enclosure heating jackets are actively warming the pack."
            else:
                return f"The battery bank is healthy at {b_soc:.1f}% SoC and {b_temp:.1f}°C. It is contributing {safe_dispatch.get('p_battery_discharge_kw')} kW to reduce diesel fuel burn."

        elif "blizzard" in q_lower or "storm" in q_lower or "wind" in q_lower:
            if wind > 25.0:
                return f"Gale winds are at {wind:.1f} m/s, so we feathered the turbine blades and applied mechanical brakes. Gensets and the battery have taken over the full load."
            else:
                return f"Winds are steady at {wind:.1f} m/s, providing {safe_dispatch.get('p_wind_kw')} kW of clean electricity. If wind exceeds 25 m/s, the system automatically brakes the turbines."

        elif "fuel" in q_lower or "saved" in q_lower:
            return f"We have saved {saved:,.0f} liters of diesel so far thanks to our wind, solar, and battery dispatch. Current burn rate is {safe_dispatch.get('fuel_rate_liters_per_hour', 14.5)} L/h."

        elif "chp" in q_lower or "heat" in q_lower:
            return f"Our Combined Heat & Power loop is delivering {safe_dispatch.get('q_chp_thermal_kwth')} kWth of captured engine heat into station living quarters, perfectly matching our heating load."

        elif any(k in q_lower for k in ["status", "system", "operations", "grid", "maitri", "bharati"]):
            return f"Station microgrid is fully stable under {telemetry.get('mode')}. Electrical load is {telemetry.get('station_load_kwe')} kWe, thermal load is {telemetry.get('thermal_load_kwth')} kWth, and renewable generation is performing nominally."

        return FALLBACK_GUARDRAIL_MSG

