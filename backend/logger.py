"""
PolarOPS - Offline Batch SQLite Database Logger
Persists all system state telemetry, MPC optimizer decisions, guardrail safety interventions,
and Groq AI natural language explanations into local sems_logs.db.
"""
import sqlite3
import json
import threading
from typing import Dict, Any, List
from backend.config import DB_PATH

class SystemEventLogger:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 1. Telemetry table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS telemetry_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        station_id TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        ambient_temp_c REAL,
                        wind_speed_ms REAL,
                        solar_irradiance_wm2 REAL,
                        station_load_kwe REAL,
                        thermal_load_kwth REAL,
                        battery_soc_pct REAL,
                        battery_temp_c REAL,
                        diesel_reserve_liters REAL
                    )
                """)

                # 2. Dispatch actions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS dispatch_actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        p_diesel_1_kw REAL,
                        p_diesel_2_kw REAL,
                        p_wind_kw REAL,
                        p_solar_kw REAL,
                        p_battery_discharge_kw REAL,
                        p_battery_charge_kw REAL,
                        q_chp_thermal_kwth REAL,
                        q_aux_thermal_kwth REAL,
                        cumulative_diesel_saved_liters REAL,
                        is_guardrail_overridden INTEGER
                    )
                """)

                # 3. Guardrail safety interventions
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS guardrail_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        rule_id TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        title TEXT NOT NULL,
                        original_val TEXT,
                        clamped_val TEXT,
                        reason TEXT
                    )
                """)

                # 4. AI explanations & chat history
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_explanations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        category TEXT NOT NULL,
                        query_or_trigger TEXT,
                        explanation TEXT
                    )
                """)
                conn.commit()

    def log_telemetry_and_dispatch(
        self,
        telemetry: Dict[str, Any],
        safe_dispatch: Dict[str, Any],
        guardrail_result: Dict[str, Any],
        explanation: str
    ):
        ts = telemetry.get("timestamp")
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Log telemetry
                    cursor.execute("""
                        INSERT INTO telemetry_logs (
                            timestamp, station_id, mode, ambient_temp_c, wind_speed_ms,
                            solar_irradiance_wm2, station_load_kwe, thermal_load_kwth,
                            battery_soc_pct, battery_temp_c, diesel_reserve_liters
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ts,
                        telemetry.get("station_id"),
                        telemetry.get("mode"),
                        telemetry.get("ambient_temp_c"),
                        telemetry.get("wind_speed_ms"),
                        telemetry.get("solar_irradiance_wm2"),
                        telemetry.get("station_load_kwe"),
                        telemetry.get("thermal_load_kwth"),
                        telemetry.get("battery_soc_pct"),
                        telemetry.get("battery_temp_c"),
                        telemetry.get("diesel_reserve_liters")
                    ))
                    
                    # Log dispatch action
                    is_overridden = 1 if guardrail_result.get("is_overridden") else 0
                    cursor.execute("""
                        INSERT INTO dispatch_actions (
                            timestamp, p_diesel_1_kw, p_diesel_2_kw, p_wind_kw, p_solar_kw,
                            p_battery_discharge_kw, p_battery_charge_kw, q_chp_thermal_kwth,
                            q_aux_thermal_kwth, cumulative_diesel_saved_liters, is_guardrail_overridden
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ts,
                        safe_dispatch.get("p_diesel_1_kw"),
                        safe_dispatch.get("p_diesel_2_kw"),
                        safe_dispatch.get("p_wind_kw"),
                        safe_dispatch.get("p_solar_kw"),
                        safe_dispatch.get("p_battery_discharge_kw"),
                        safe_dispatch.get("p_battery_charge_kw"),
                        safe_dispatch.get("q_chp_thermal_kwth"),
                        safe_dispatch.get("q_aux_thermal_kwth"),
                        safe_dispatch.get("cumulative_diesel_saved_liters"),
                        is_overridden
                    ))

                    # Log any guardrail interventions
                    for inv in guardrail_result.get("interventions", []):
                        cursor.execute("""
                            INSERT INTO guardrail_events (
                                timestamp, rule_id, severity, title, original_val, clamped_val, reason
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            ts,
                            inv.get("rule_id"),
                            inv.get("severity"),
                            inv.get("title"),
                            inv.get("original_val"),
                            inv.get("clamped_val"),
                            inv.get("reason")
                        ))

                    # Log AI explanation
                    if explanation:
                        cursor.execute("""
                            INSERT INTO ai_explanations (
                                timestamp, category, query_or_trigger, explanation
                            ) VALUES (?, ?, ?, ?)
                        """, (
                            ts,
                            "DISPATCH_EXPLANATION" if not is_overridden else "GUARDRAIL_EXPLANATION",
                            "AUTO_TELEMETRY_STEP",
                            explanation
                        ))

                    conn.commit()
            except Exception as e:
                print(f"[Logger Error] Failed to commit logs: {e}")

    def log_chat_interaction(self, query: str, answer: str):
        import datetime
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO ai_explanations (timestamp, category, query_or_trigger, explanation)
                        VALUES (?, ?, ?, ?)
                    """, (ts, "COMMANDER_CHAT", query, answer))
                    conn.commit()
            except Exception as e:
                print(f"[Logger Error] Failed to log chat: {e}")

    def get_recent_history(self, limit: int = 30) -> Dict[str, Any]:
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM telemetry_logs ORDER BY id DESC LIMIT ?", (limit,))
                    telemetry_rows = [dict(row) for row in cursor.fetchall()]
                    
                    cursor.execute("SELECT * FROM guardrail_events ORDER BY id DESC LIMIT ?", (limit,))
                    guardrail_rows = [dict(row) for row in cursor.fetchall()]

                    cursor.execute("SELECT * FROM ai_explanations ORDER BY id DESC LIMIT ?", (limit,))
                    ai_rows = [dict(row) for row in cursor.fetchall()]

                    return {
                        "telemetry": list(reversed(telemetry_rows)),
                        "guardrail_events": guardrail_rows,
                        "ai_explanations": ai_rows
                    }
            except Exception as e:
                print(f"[Logger Error] Fetch failed: {e}")
                return {"telemetry": [], "guardrail_events": [], "ai_explanations": []}
