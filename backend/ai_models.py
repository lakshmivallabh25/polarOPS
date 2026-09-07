"""
PolarOPS - Predictive AI Forecasting Engine
Utilizes LightGBM gradient boosted decision trees to forecast 24-hour Electrical (kWe)
and Thermal (kWth) demand trajectories based on weather and station profiles.
"""
import numpy as np
import lightgbm as lgb
from typing import Dict, List, Any
import datetime
import random
from backend.config import STATIONS, WIND_CUT_IN_MS, WIND_RATED_MS, WIND_CUT_OUT_MS

class PolarDemandForecaster:
    def __init__(self):
        self.is_trained = False
        self.model_elec = None
        self.model_therm = None
        self._initialize_and_train_models()

    def _initialize_and_train_models(self):
        """
        Trains LightGBM regressors on synthetic polar physics data
        to predict electrical and thermal loads.
        Features: [hour_of_day, ambient_temp_c, wind_speed_ms, solar_irradiance_wm2, base_load_kwe, base_thermal_kwth]
        """
        np.random.seed(42)
        n_samples = 4000
        
        hours = np.random.randint(0, 24, n_samples)
        temps = np.random.uniform(-45.0, 0.0, n_samples)
        winds = np.random.uniform(0.0, 30.0, n_samples)
        solars = np.maximum(0.0, np.random.uniform(-50.0, 450.0, n_samples))
        base_e = np.random.choice([48.0, 56.0], n_samples)
        base_th = np.random.choice([62.0, 72.0], n_samples)
        
        # Physics ground truth relationships:
        # 1. Electrical: Base load + diurnal schedule (lab operations 08:00 - 18:00) + auxiliary heat pumping if severe cold
        diurnal_elec = 8.0 * np.sin(np.maximum(0.0, (hours - 7) / 11 * np.pi))
        cold_elec_boost = np.maximum(0.0, (-20.0 - temps) * 0.4)
        target_elec = base_e + diurnal_elec + cold_elec_boost + np.random.normal(0, 1.5, n_samples)
        
        # 2. Thermal: Base heating + conductive building loss (proportional to delta T) + convective wind chill
        delta_t_loss = np.maximum(0.0, (20.0 - temps) * 1.35)
        wind_convection = winds * 0.75
        target_therm = base_th + delta_t_loss + wind_convection + np.random.normal(0, 2.0, n_samples)
        
        X = np.column_stack([hours, temps, winds, solars, base_e, base_th])
        
        # Train LightGBM models
        params = {
            'objective': 'regression',
            'metric': 'rmse',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'n_estimators': 60,
            'verbose': -1
        }
        
        self.model_elec = lgb.LGBMRegressor(**params)
        self.model_elec.fit(X, target_elec)
        
        self.model_therm = lgb.LGBMRegressor(**params)
        self.model_therm.fit(X, target_therm)
        
        self.is_trained = True

    def calculate_wind_power(self, wind_speed: float, capacity_kw: float) -> float:
        """Aerodynamic polar wind turbine power curve with storm cut-out feathering"""
        if wind_speed < WIND_CUT_IN_MS:
            return 0.0
        elif wind_speed > WIND_CUT_OUT_MS:
            # Blizzard storm shutdown to protect mechanical gearbox
            return 0.0
        elif wind_speed >= WIND_RATED_MS:
            return capacity_kw
        else:
            # Cubic aerodynamic ramp between cut-in and rated
            fraction = ((wind_speed - WIND_CUT_IN_MS) / (WIND_RATED_MS - WIND_CUT_IN_MS)) ** 3
            return capacity_kw * fraction

    def calculate_solar_power(self, irradiance_wm2: float, capacity_kw: float) -> float:
        """Bifacial polar solar generation accounting for snow blue-ice albedo (1.20x factor)"""
        # Standard test conditions: 1000 W/m2
        albedo_factor = 1.20
        eff = min(1.0, (irradiance_wm2 / 1000.0) * albedo_factor)
        return capacity_kw * eff

    def predict_horizon(self, telemetry: Dict[str, Any], horizon: str = "24 Hours") -> Dict[str, Any]:
        """
        Produces lookahead projection for Electrical, Thermal, Wind, and Solar trajectories
        across extended horizons:
        ['24 Hours', 'Tomorrow', 'Current Week', 'Next 2-3 Weeks', '1 Month', '3 Months', '6 Months', '12 Months']
        """
        station_id = telemetry.get("station_id", "MAITRI")
        station = STATIONS.get(station_id, STATIONS["MAITRI"])
        base_temp = float(telemetry.get("ambient_temp_c", -20.0))
        base_wind = float(telemetry.get("wind_speed_ms", 10.0))
        
        try:
            current_time = datetime.datetime.fromisoformat(telemetry.get("timestamp", ""))
        except Exception:
            current_time = datetime.datetime.now(datetime.timezone.utc)

        # Normalize horizon string
        h_clean = horizon.strip()

        labels = []
        timestamps = []
        pred_elec = []
        pred_therm = []
        pred_wind_kw = []
        pred_solar_kw = []

        if h_clean == "Tomorrow":
            # 24 hours for the next calendar day
            start_tomorrow = current_time + datetime.timedelta(days=1)
            for h in range(24):
                ft = start_tomorrow.replace(hour=h, minute=0, second=0, microsecond=0)
                labels.append(f"{h:02d}:00")
                timestamps.append(ft.isoformat())
                
                temp_h = base_temp + 3.5 * np.sin((h - 8) * np.pi / 12) + random.uniform(-0.5, 0.5)
                wind_h = max(0.5, base_wind + 3.0 * np.cos((h - 5) * np.pi / 12))
                solar_h = max(0.0, 310.0 * np.sin((h - 5) * np.pi / 14)) if 5 <= h <= 19 else 0.0
                
                feat = np.array([[h, temp_h, wind_h, solar_h, station["base_load_kwe"], station["base_thermal_kwth"]]])
                pe = float(self.model_elec.predict(feat)[0])
                pt = float(self.model_therm.predict(feat)[0])
                
                pred_elec.append(round(pe, 1))
                pred_therm.append(round(pt, 1))
                pred_wind_kw.append(round(self.calculate_wind_power(wind_h, station["wind_capacity_kw"]), 1))
                pred_solar_kw.append(round(self.calculate_solar_power(solar_h, station["solar_capacity_kw"]), 1))

        elif h_clean == "Current Week":
            # 7 daily projections
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            for d in range(7):
                ft = current_time + datetime.timedelta(days=d)
                labels.append(ft.strftime("%a %d"))
                timestamps.append(ft.isoformat())
                
                day_temp = base_temp + 2.0 * np.sin(d * 0.8) + random.uniform(-1.0, 1.0)
                day_wind = max(2.0, base_wind + 3.0 * np.cos(d * 1.1))
                day_solar = 220.0 + 40.0 * np.sin(d * 0.5)
                
                feat = np.array([[12, day_temp, day_wind, day_solar, station["base_load_kwe"], station["base_thermal_kwth"]]])
                pred_elec.append(round(float(self.model_elec.predict(feat)[0]), 1))
                pred_therm.append(round(float(self.model_therm.predict(feat)[0]), 1))
                pred_wind_kw.append(round(self.calculate_wind_power(day_wind, station["wind_capacity_kw"]) * 0.75, 1))
                pred_solar_kw.append(round(self.calculate_solar_power(day_solar, station["solar_capacity_kw"]) * 0.65, 1))

        elif h_clean == "Next 2-3 Weeks":
            # 21 daily projections
            for d in range(21):
                ft = current_time + datetime.timedelta(days=d)
                labels.append(ft.strftime("%d %b") if d % 3 == 0 or d == 20 else "")
                timestamps.append(ft.isoformat())
                
                weather_drift = -0.15 * d  # Season trend
                day_temp = base_temp + weather_drift + 3.0 * np.sin(d * 0.6)
                day_wind = max(1.5, base_wind + 3.5 * np.cos(d * 0.45))
                day_solar = max(0.0, 240.0 - 5.0 * d + 30.0 * np.sin(d * 0.5))
                
                feat = np.array([[13, day_temp, day_wind, day_solar, station["base_load_kwe"], station["base_thermal_kwth"]]])
                pred_elec.append(round(float(self.model_elec.predict(feat)[0]), 1))
                pred_therm.append(round(float(self.model_therm.predict(feat)[0]), 1))
                pred_wind_kw.append(round(self.calculate_wind_power(day_wind, station["wind_capacity_kw"]) * 0.72, 1))
                pred_solar_kw.append(round(self.calculate_solar_power(day_solar, station["solar_capacity_kw"]) * 0.60, 1))

        elif h_clean == "1 Month":
            # 30 daily steps
            for d in range(30):
                ft = current_time + datetime.timedelta(days=d)
                labels.append(f"Day {d+1}" if d % 5 == 0 or d == 29 else "")
                timestamps.append(ft.isoformat())
                
                day_temp = base_temp - 0.2 * d + 2.5 * np.sin(d * 0.4)
                day_wind = max(2.0, base_wind + 4.0 * np.cos(d * 0.35))
                day_solar = max(0.0, 250.0 - 6.0 * d)
                
                feat = np.array([[12, day_temp, day_wind, day_solar, station["base_load_kwe"], station["base_thermal_kwth"]]])
                pred_elec.append(round(float(self.model_elec.predict(feat)[0]), 1))
                pred_therm.append(round(float(self.model_therm.predict(feat)[0]), 1))
                pred_wind_kw.append(round(self.calculate_wind_power(day_wind, station["wind_capacity_kw"]) * 0.70, 1))
                pred_solar_kw.append(round(self.calculate_solar_power(day_solar, station["solar_capacity_kw"]) * 0.55, 1))

        elif h_clean == "3 Months":
            # 12 weekly aggregated steps
            for w in range(12):
                labels.append(f"Wk {w+1}")
                timestamps.append((current_time + datetime.timedelta(weeks=w)).isoformat())
                
                week_temp = base_temp - 1.2 * w + 2.0 * np.sin(w)
                week_wind = max(3.0, base_wind + 3.0 * np.cos(w * 0.8))
                week_solar = max(0.0, 280.0 - 22.0 * w)
                
                feat = np.array([[12, week_temp, week_wind, week_solar, station["base_load_kwe"], station["base_thermal_kwth"]]])
                pred_elec.append(round(float(self.model_elec.predict(feat)[0]), 1))
                pred_therm.append(round(float(self.model_therm.predict(feat)[0]), 1))
                pred_wind_kw.append(round(self.calculate_wind_power(week_wind, station["wind_capacity_kw"]) * 0.75, 1))
                pred_solar_kw.append(round(self.calculate_solar_power(week_solar, station["solar_capacity_kw"]) * 0.50, 1))

        elif h_clean == "6 Months":
            # 6 monthly seasonal steps
            month_names = ["Mth 1", "Mth 2", "Mth 3", "Mth 4", "Mth 5", "Mth 6"]
            for m in range(6):
                ft = current_time + datetime.timedelta(days=m*30)
                labels.append(ft.strftime("%b"))
                timestamps.append(ft.isoformat())
                
                # Polar seasonal transition curve
                m_temp = base_temp - 3.5 * m + 3.0 * np.sin(m)
                m_wind = max(4.0, base_wind + 4.0 * np.cos(m * 0.9))
                m_solar = max(0.0, 300.0 - 55.0 * m)
                
                feat = np.array([[12, m_temp, m_wind, m_solar, station["base_load_kwe"], station["base_thermal_kwth"]]])
                pred_elec.append(round(float(self.model_elec.predict(feat)[0]), 1))
                pred_therm.append(round(float(self.model_therm.predict(feat)[0]), 1))
                pred_wind_kw.append(round(self.calculate_wind_power(m_wind, station["wind_capacity_kw"]) * 0.72, 1))
                pred_solar_kw.append(round(self.calculate_solar_power(m_solar, station["solar_capacity_kw"]) * 0.45, 1))

        elif h_clean == "12 Months":
            # Full 12-month polar annual cycle (Solstice to Solstice)
            months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            for m_idx, m_name in enumerate(months):
                labels.append(m_name)
                # Polar physics: Jan/Dec is polar summer; Jun/Jul is polar night (0 solar, -40C)
                # Cosine wave peak at summer (Jan = idx 0), trough at winter (Jul = idx 6)
                solstice_angle = (m_idx / 12.0) * 2 * np.pi
                m_temp = -28.0 + 16.0 * np.cos(solstice_angle)
                m_wind = 12.0 - 3.0 * np.cos(solstice_angle) # Stronger winter blizzards
                # Polar night in Antarctica: May (4), Jun (5), Jul (6), Aug (7) have near zero or 0 solar
                solar_intensity = max(0.0, 360.0 * np.cos(solstice_angle)) if m_idx in [10, 11, 0, 1, 2] else (30.0 if m_idx in [3, 8, 9] else 0.0)
                
                feat = np.array([[12, m_temp, m_wind, solar_intensity, station["base_load_kwe"], station["base_thermal_kwth"]]])
                pred_elec.append(round(float(self.model_elec.predict(feat)[0]), 1))
                pred_therm.append(round(float(self.model_therm.predict(feat)[0]), 1))
                pred_wind_kw.append(round(self.calculate_wind_power(m_wind, station["wind_capacity_kw"]) * 0.70, 1))
                pred_solar_kw.append(round(self.calculate_solar_power(solar_intensity, station["solar_capacity_kw"]) * 0.60, 1))

        else:
            # Default: 24 Hours
            h_clean = "24 Hours"
            for h in range(24):
                forecast_time = current_time + datetime.timedelta(hours=h)
                target_hour = forecast_time.hour
                labels.append(f"{target_hour:02d}:00")
                timestamps.append(forecast_time.isoformat())
                
                temp_h = base_temp + 4.0 * np.sin((target_hour - 9) * np.pi / 12)
                wind_h = max(0.5, base_wind + 2.5 * np.cos((target_hour - 4) * np.pi / 12))
                solar_h = max(0.0, 340.0 * np.sin((target_hour - 5) * np.pi / 14)) if 5 <= target_hour <= 19 else 0.0
                
                feat = np.array([[target_hour, temp_h, wind_h, solar_h, station["base_load_kwe"], station["base_thermal_kwth"]]])
                pred_elec.append(round(float(self.model_elec.predict(feat)[0]), 1))
                pred_therm.append(round(float(self.model_therm.predict(feat)[0]), 1))
                pred_wind_kw.append(round(self.calculate_wind_power(wind_h, station["wind_capacity_kw"]), 1))
                pred_solar_kw.append(round(self.calculate_solar_power(solar_h, station["solar_capacity_kw"]), 1))

        net_load = [
            round(max(0.0, pred_elec[i] - (pred_wind_kw[i] + pred_solar_kw[i])), 1)
            for i in range(len(pred_elec))
        ]

        return {
            "horizon": h_clean,
            "hours": labels,
            "timestamps": timestamps,
            "electrical_kwe": pred_elec,
            "thermal_kwth": pred_therm,
            "wind_available_kw": pred_wind_kw,
            "solar_available_kw": pred_solar_kw,
            "net_electrical_kwe": net_load
        }

    def predict_24h(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """Backward-compatible helper for 24-hour horizon"""
        return self.predict_horizon(telemetry, "24 Hours")

