"""
PolarOPS - Model Predictive Control (MPC) & Linear Programming Optimizer
Minimizes diesel fuel consumption while satisfying electrical, Combined Heat & Power (CHP) thermal,
and temperature-dependent battery capacity derating constraints using SciPy linprog.
"""
import numpy as np
from scipy.optimize import linprog
from typing import Dict, Any, Tuple
from backend.config import (
    STATIONS,
    DIESEL_SPECIFIC_CONSUMPTION,
    DIESEL_MIN_LOAD_PCT,
    CHP_THERMAL_RATIO,
    BATTERY_MIN_SOC_PCT,
    BATTERY_MAX_SOC_PCT,
    BATTERY_DERATE_TEMP_C,
    BATTERY_LOCKOUT_TEMP_C
)

class PolarEnergyOptimizer:
    def __init__(self):
        self.cumulative_diesel_saved_liters = 4280.0 # Initial historical base for demo
        self.cumulative_co2_avoided_kg = round(4280.0 * 2.68, 1)

    def calculate_battery_derating(self, battery_temp_c: float, soc_pct: float, nominal_capacity_kwh: float) -> Tuple[float, float, float]:
        """
        Calculates temperature-dependent battery derating factor and max charge/discharge limits.
        Below -20°C, LiFePO4 internal impedance rises sharply, derating effective kW throughput.
        Below -35°C, discharge is locked out completely without pre-heaters.
        """
        # 1. Temperature derating factor
        if battery_temp_c >= BATTERY_DERATE_TEMP_C:
            temp_factor = 1.0
        elif battery_temp_c <= BATTERY_LOCKOUT_TEMP_C:
            temp_factor = 0.05 # Near zero discharge capacity
        else:
            # Linear degradation from -20C (1.0) down to -35C (0.05)
            temp_factor = 0.05 + 0.95 * (battery_temp_c - BATTERY_LOCKOUT_TEMP_C) / (BATTERY_DERATE_TEMP_C - BATTERY_LOCKOUT_TEMP_C)
            
        effective_capacity_kwh = nominal_capacity_kwh * temp_factor
        
        # 2. Maximum discharge rate (0.7C nominal, scaled by temp and available SoC headroom)
        max_c_rate = 0.7
        nominal_max_kw = nominal_capacity_kwh * max_c_rate
        
        if soc_pct <= BATTERY_MIN_SOC_PCT or temp_factor < 0.1:
            max_discharge_kw = 0.0
        else:
            soc_headroom = (soc_pct - BATTERY_MIN_SOC_PCT) / (100.0 - BATTERY_MIN_SOC_PCT)
            max_discharge_kw = nominal_max_kw * temp_factor * min(1.0, soc_headroom * 1.5)
            
        # 3. Maximum charge rate (charging sub-zero batteries causes lithium plating if too fast)
        charge_temp_factor = max(0.1, temp_factor * 0.8)
        if soc_pct >= BATTERY_MAX_SOC_PCT:
            max_charge_kw = 0.0
        else:
            charge_headroom = (BATTERY_MAX_SOC_PCT - soc_pct) / (BATTERY_MAX_SOC_PCT - BATTERY_MIN_SOC_PCT)
            max_charge_kw = (nominal_capacity_kwh * 0.5) * charge_temp_factor * min(1.0, charge_headroom * 1.2)
            
        return round(temp_factor, 3), round(max_discharge_kw, 1), round(max_charge_kw, 1)

    def optimize_dispatch(self, telemetry: Dict[str, Any], wind_avail_kw: float, solar_avail_kw: float) -> Dict[str, Any]:
        """
        Linear Programming Formulation:
        Variables vector x:
        0: P_diesel_1   (kW)
        1: P_diesel_2   (kW)
        2: P_wind       (kW)
        3: P_solar      (kW)
        4: P_batt_dis   (kW - Battery discharging into grid)
        5: P_batt_chg   (kW - Battery absorbing excess renewable)
        6: Q_aux_heat   (kWth - Electric boiler auxiliary thermal)
        7: P_curtail    (kW - Renewable curtailment if bus saturated)
        """
        station_id = telemetry.get("station_id", "MAITRI")
        station = STATIONS.get(station_id, STATIONS["MAITRI"])
        
        p_load_e = float(telemetry.get("station_load_kwe", 50.0))
        q_load_th = float(telemetry.get("thermal_load_kwth", 65.0))
        battery_temp_c = float(telemetry.get("battery_temp_c", -12.0))
        soc_pct = float(telemetry.get("battery_soc_pct", 75.0))
        genset_1_fault = bool(telemetry.get("genset_1_fault", False))
        
        # Calculate battery derated limits
        temp_factor, max_batt_dis, max_batt_chg = self.calculate_battery_derating(
            battery_temp_c, soc_pct, station["battery_capacity_kwh"]
        )

        # Diesel capacities
        gen1_max = 0.0 if genset_1_fault else station["genset_1_max_kw"]
        gen2_max = station["genset_2_max_kw"]

        # Objective Function Weights (Cost vector c)
        # We heavily penalize burning diesel fuel and auxiliary electric heat
        c = [
            100.0,   # P_diesel_1 ($ fuel cost + emissions)
            115.0,   # P_diesel_2 (secondary genset slightly higher dispatch order)
            0.01,    # P_wind (practically free)
            0.01,    # P_solar (practically free)
            1.50,    # P_batt_dis (slight battery degradation cost)
            -0.80,   # P_batt_chg (incentive to charge battery from green power)
            45.0,    # Q_aux_heat (auxiliary thermal heater)
            5.00     # P_curtail (curtailment penalty - prioritize using or storing)
        ]

        # Equality Constraint: Electrical Power Balance
        # P_diesel_1 + P_diesel_2 + P_wind + P_solar + P_batt_dis - P_batt_chg - P_curtail = P_load_e
        A_eq = [
            [1.0, 1.0, 1.0, 1.0, 1.0, -1.0, 0.0, -1.0]
        ]
        b_eq = [p_load_e]

        # Inequality Constraint: Thermal Power Balance (CHP)
        # CHP heat recovered from diesel + Q_aux_heat >= Q_load_th
        # => - CHP_ratio * P_diesel_1 - CHP_ratio * P_diesel_2 - Q_aux_heat <= - Q_load_th
        A_ub = [
            [-CHP_THERMAL_RATIO, -CHP_THERMAL_RATIO, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0]
        ]
        b_ub = [-q_load_th]

        # Bounds on variables
        bounds = [
            (0.0, gen1_max),              # P_diesel_1
            (0.0, gen2_max),              # P_diesel_2
            (0.0, max(0.0, wind_avail_kw)),  # P_wind
            (0.0, max(0.0, solar_avail_kw)), # P_solar
            (0.0, max_batt_dis),          # P_batt_dis
            (0.0, max_batt_chg),          # P_batt_chg
            (0.0, 150.0),                 # Q_aux_heat
            (0.0, 250.0)                  # P_curtail
        ]

        # Solve Linear Program using HiGHS
        res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")

        if res.success:
            x = res.x
            p_gen1 = max(0.0, float(x[0]))
            p_gen2 = max(0.0, float(x[1]))
            p_wind = max(0.0, float(x[2]))
            p_solar = max(0.0, float(x[3]))
            p_dis = max(0.0, float(x[4]))
            p_chg = max(0.0, float(x[5]))
            q_aux = max(0.0, float(x[6]))
            p_curt = max(0.0, float(x[7]))
        else:
            # Emergency deterministic fallback if LP fails
            p_gen1 = gen1_max * 0.6 if not genset_1_fault else 0.0
            p_gen2 = gen2_max * 0.7 if genset_1_fault else 0.0
            p_wind = min(wind_avail_kw, p_load_e * 0.4)
            p_solar = min(solar_avail_kw, p_load_e * 0.2)
            p_dis = 0.0
            p_chg = 0.0
            q_aux = max(0.0, q_load_th - (p_gen1 + p_gen2) * CHP_THERMAL_RATIO)
            p_curt = 0.0

        # Thermal heat recovered via Combined Heat & Power (CHP)
        total_diesel_e = p_gen1 + p_gen2
        q_chp_recovered = total_diesel_e * CHP_THERMAL_RATIO
        total_thermal_supplied = q_chp_recovered + q_aux

        # Compute fuel consumption & cumulative savings
        # Baseline fuel if no renewables: diesel must supply all p_load_e + electric heating for q_load_th
        baseline_elec_kwh = p_load_e
        baseline_fuel_l = baseline_elec_kwh * DIESEL_SPECIFIC_CONSUMPTION * (1.0 / 3600.0)
        
        actual_fuel_l = total_diesel_e * DIESEL_SPECIFIC_CONSUMPTION * (1.0 / 3600.0)
        fuel_saved_step_l = max(0.0, baseline_fuel_l - actual_fuel_l)
        
        self.cumulative_diesel_saved_liters += fuel_saved_step_l
        self.cumulative_co2_avoided_kg += fuel_saved_step_l * 2.68

        # Dispatch percentages
        total_gen = p_gen1 + p_gen2 + p_wind + p_solar + p_dis
        if total_gen > 0:
            pct_wind = round((p_wind / total_gen) * 100.0, 1)
            pct_solar = round((p_solar / total_gen) * 100.0, 1)
            pct_diesel = round(((p_gen1 + p_gen2) / total_gen) * 100.0, 1)
            pct_battery = round((p_dis / total_gen) * 100.0, 1)
        else:
            pct_wind = pct_solar = pct_battery = 0.0
            pct_diesel = 100.0

        return {
            "p_diesel_1_kw": round(p_gen1, 1),
            "p_diesel_2_kw": round(p_gen2, 1),
            "p_wind_kw": round(p_wind, 1),
            "p_solar_kw": round(p_solar, 1),
            "p_battery_discharge_kw": round(p_dis, 1),
            "p_battery_charge_kw": round(p_chg, 1),
            "p_curtailment_kw": round(p_curt, 1),
            "q_chp_thermal_kwth": round(q_chp_recovered, 1),
            "q_aux_thermal_kwth": round(q_aux, 1),
            "total_thermal_kwth": round(total_thermal_supplied, 1),
            "battery_derating_factor": temp_factor,
            "battery_max_discharge_kw": max_batt_dis,
            "fuel_rate_liters_per_hour": round(total_diesel_e * DIESEL_SPECIFIC_CONSUMPTION, 2),
            "cumulative_diesel_saved_liters": round(self.cumulative_diesel_saved_liters, 1),
            "cumulative_co2_avoided_kg": round(self.cumulative_co2_avoided_kg, 1),
            "dispatch_split": {
                "wind_pct": pct_wind,
                "solar_pct": pct_solar,
                "diesel_pct": pct_diesel,
                "battery_pct": pct_battery
            }
        }
