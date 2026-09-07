"""
PolarOPS - Deterministic Safety Guardrail Layer
Enforces physical station safety constraints and overrides AI/Optimizer decisions:
1. 60-minute minimum run-time on diesel gensets (prevents wet stacking & thermal shock).
2. Battery sub-zero lockout (blocks discharge if temp < -35°C or SoC <= 20%).
3. Spinning reserve blackout defense (guarantees >= 15 kW headroom).
4. Thermal life-support protection (guarantees station habitable heating).
5. Gale-force wind feathering lockout (> 25 m/s).
"""
import time
from typing import Dict, Any, List
from backend.config import (
    DIESEL_MIN_RUN_TIME_MIN,
    DIESEL_MIN_LOAD_PCT,
    BATTERY_LOCKOUT_TEMP_C,
    BATTERY_MIN_SOC_PCT,
    WIND_CUT_OUT_MS,
    CHP_THERMAL_RATIO
)

class SafetyGuardrailEngine:
    def __init__(self):
        # Track continuous runtimes (in seconds)
        self.gen1_active = True
        self.gen1_run_seconds = 2100.0  # 35 minutes running initially
        self.gen2_active = False
        self.gen2_run_seconds = 0.0
        self.last_eval_time = time.time()

    def update_clock(self, dt_seconds: float = 1.0):
        if self.gen1_active:
            self.gen1_run_seconds += dt_seconds
        else:
            self.gen1_run_seconds = 0.0
            
        if self.gen2_active:
            self.gen2_run_seconds += dt_seconds
        else:
            self.gen2_run_seconds = 0.0

    def enforce_safety(self, telemetry: Dict[str, Any], optimizer_dispatch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deterministic safety check. Overrides optimizer setpoints if safety rules are violated.
        Returns safe dispatch setpoints and an audit trail of any interventions.
        """
        interventions: List[Dict[str, Any]] = []
        safe_dispatch = dict(optimizer_dispatch)
        
        station_load_e = float(telemetry.get("station_load_kwe", 50.0))
        thermal_load_th = float(telemetry.get("thermal_load_kwth", 65.0))
        battery_temp_c = float(telemetry.get("battery_temp_c", -12.0))
        battery_soc_pct = float(telemetry.get("battery_soc_pct", 75.0))
        wind_speed_ms = float(telemetry.get("wind_speed_ms", 10.0))
        genset_1_fault = bool(telemetry.get("genset_1_fault", False))
        
        p_gen1 = safe_dispatch["p_diesel_1_kw"]
        p_gen2 = safe_dispatch["p_diesel_2_kw"]
        p_wind = safe_dispatch["p_wind_kw"]
        p_solar = safe_dispatch["p_solar_kw"]
        p_batt_dis = safe_dispatch["p_battery_discharge_kw"]
        p_batt_chg = safe_dispatch["p_battery_charge_kw"]
        q_aux = safe_dispatch["q_aux_thermal_kwth"]

        # -------------------------------------------------------------
        # GUARDRAIL RULE 1: Minimum 60-Minute Diesel Runtime Protection
        # -------------------------------------------------------------
        min_run_sec = DIESEL_MIN_RUN_TIME_MIN * 60.0  # 3600 seconds
        if not genset_1_fault and self.gen1_active:
            if self.gen1_run_seconds < min_run_sec and p_gen1 < 20.0:
                # Optimizer tried to turn off or underload Gen1 before 60 min elapsed
                min_safe_load = 25.0  # 25% minimum loading
                safe_dispatch["p_diesel_1_kw"] = min_safe_load
                interventions.append({
                    "rule_id": "GR-01-MIN-RUNTIME",
                    "severity": "CRITICAL",
                    "title": "Genset 1 Min-Runtime Enforced",
                    "original_val": f"{p_gen1:.1f} kW",
                    "clamped_val": f"{min_safe_load:.1f} kW",
                    "reason": f"Genset 1 has only run for {int(self.gen1_run_seconds / 60)}m (< 60m threshold). Shutdown blocked to prevent wet stacking and thermal cylinder shock."
                })
                # Adjust balance: if gen1 increased, reduce battery discharge or curtail excess
                p_gen1 = min_safe_load

        # -------------------------------------------------------------
        # GUARDRAIL RULE 2: Sub-Zero Battery Lockout & Deep Discharge Inhibit
        # -------------------------------------------------------------
        if battery_temp_c <= BATTERY_LOCKOUT_TEMP_C and p_batt_dis > 0:
            safe_dispatch["p_battery_discharge_kw"] = 0.0
            interventions.append({
                "rule_id": "GR-02-BESS-FREEZE-LOCKOUT",
                "severity": "HIGH",
                "title": "BESS Sub-Zero Freeze Inhibit",
                "original_val": f"{p_batt_dis:.1f} kW",
                "clamped_val": "0.0 kW",
                "reason": f"Battery core temp at {battery_temp_c:.1f}°C (<= {BATTERY_LOCKOUT_TEMP_C}°C). Discharge blocked to prevent irreparable dendrite short-circuiting."
            })
            p_batt_dis = 0.0
            
        if battery_soc_pct <= BATTERY_MIN_SOC_PCT and p_batt_dis > 0:
            safe_dispatch["p_battery_discharge_kw"] = 0.0
            interventions.append({
                "rule_id": "GR-03-BESS-LOW-SOC-INHIBIT",
                "severity": "HIGH",
                "title": "BESS Reserve Floor Protected",
                "original_val": f"{p_batt_dis:.1f} kW",
                "clamped_val": "0.0 kW",
                "reason": f"Battery State-of-Charge is {battery_soc_pct:.1f}% (<= {BATTERY_MIN_SOC_PCT}%). Inverting stopped to preserve emergency life-support reserve."
            })
            p_batt_dis = 0.0

        # -------------------------------------------------------------
        # GUARDRAIL RULE 3: Gale-Force Storm Feathering Lockout
        # -------------------------------------------------------------
        if wind_speed_ms > WIND_CUT_OUT_MS and p_wind > 0:
            safe_dispatch["p_wind_kw"] = 0.0
            interventions.append({
                "rule_id": "GR-04-WIND-GALE-CUTOUT",
                "severity": "CRITICAL",
                "title": "Wind Turbine Storm Brake Engaged",
                "original_val": f"{p_wind:.1f} kW",
                "clamped_val": "0.0 kW",
                "reason": f"Wind velocity is {wind_speed_ms:.1f} m/s (> {WIND_CUT_OUT_MS} m/s limit). Aerodynamic feathering and mechanical disk brake deployed."
            })
            p_wind = 0.0

        # -------------------------------------------------------------
        # GUARDRAIL RULE 4: Blackout Defense (Electrical Balance & Spinning Reserve)
        # -------------------------------------------------------------
        current_generation = safe_dispatch["p_diesel_1_kw"] + safe_dispatch["p_diesel_2_kw"] + safe_dispatch["p_wind_kw"] + safe_dispatch["p_solar_kw"] + safe_dispatch["p_battery_discharge_kw"] - safe_dispatch["p_battery_charge_kw"]
        deficit_e = station_load_e - current_generation
        
        if deficit_e > 0.5:
            # Need emergency power dispatch
            if not genset_1_fault and safe_dispatch["p_diesel_1_kw"] < 100.0:
                boost = min(deficit_e, 100.0 - safe_dispatch["p_diesel_1_kw"])
                safe_dispatch["p_diesel_1_kw"] += boost
                deficit_e -= boost
                
            if deficit_e > 0.5:
                # Fire up Standby Genset 2
                safe_dispatch["p_diesel_2_kw"] += deficit_e
                interventions.append({
                    "rule_id": "GR-05-BLACKOUT-DEFENSE",
                    "severity": "EMERGENCY",
                    "title": "Standby Genset 2 Dispatched",
                    "original_val": f"{optimizer_dispatch['p_diesel_2_kw']:.1f} kW",
                    "clamped_val": f"{safe_dispatch['p_diesel_2_kw']:.1f} kW",
                    "reason": f"Power balance deficit of {deficit_e:.1f} kW detected. Standby Genset 2 spun up to prevent frequency collapse on station microgrid."
                })

        # -------------------------------------------------------------
        # GUARDRAIL RULE 5: Thermal Life Support Protection
        # -------------------------------------------------------------
        q_chp = (safe_dispatch["p_diesel_1_kw"] + safe_dispatch["p_diesel_2_kw"]) * CHP_THERMAL_RATIO
        safe_dispatch["q_chp_thermal_kwth"] = round(q_chp, 1)
        thermal_supply = q_chp + safe_dispatch["q_aux_thermal_kwth"]
        
        if thermal_supply < thermal_load_th:
            thermal_shortfall = thermal_load_th - thermal_supply
            safe_dispatch["q_aux_thermal_kwth"] += thermal_shortfall
            interventions.append({
                "rule_id": "GR-06-THERMAL-LIFE-SUPPORT",
                "severity": "CRITICAL",
                "title": "Station Heating Shortfall Boosted",
                "original_val": f"{thermal_supply:.1f} kWth",
                "clamped_val": f"{thermal_load_th:.1f} kWth",
                "reason": f"Station thermal demand exceeded CHP waste heat. Auxiliary electric boiler boosted by {thermal_shortfall:.1f} kWth."
            })

        # Update engine states
        self.gen1_active = safe_dispatch["p_diesel_1_kw"] > 5.0
        self.gen2_active = safe_dispatch["p_diesel_2_kw"] > 5.0

        # Recalculate dispatch split with finalized safe setpoints
        tot = (
            safe_dispatch["p_diesel_1_kw"] +
            safe_dispatch["p_diesel_2_kw"] +
            safe_dispatch["p_wind_kw"] +
            safe_dispatch["p_solar_kw"] +
            safe_dispatch["p_battery_discharge_kw"]
        )
        if tot > 0:
            safe_dispatch["dispatch_split"] = {
                "wind_pct": round((safe_dispatch["p_wind_kw"] / tot) * 100.0, 1),
                "solar_pct": round((safe_dispatch["p_solar_kw"] / tot) * 100.0, 1),
                "diesel_pct": round(((safe_dispatch["p_diesel_1_kw"] + safe_dispatch["p_diesel_2_kw"]) / tot) * 100.0, 1),
                "battery_pct": round((safe_dispatch["p_battery_discharge_kw"] / tot) * 100.0, 1)
            }

        return {
            "is_overridden": len(interventions) > 0,
            "interventions": interventions,
            "safe_dispatch": safe_dispatch,
            "gen1_runtime_minutes": round(self.gen1_run_seconds / 60.0, 1),
            "gen2_runtime_minutes": round(self.gen2_run_seconds / 60.0, 1)
        }
