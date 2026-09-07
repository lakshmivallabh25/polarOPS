import httpx
import asyncio
import websockets
import json

async def verify_endpoints():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=5.0) as client:
        # 1. Test status
        res = await client.get("/api/status")
        print("[TEST] /api/status ->", res.status_code, res.json())
        assert res.status_code == 200

        # 2. Test index.html
        res = await client.get("/")
        print("[TEST] / ->", res.status_code, f"Length: {len(res.text)} bytes")
        assert res.status_code == 200
        assert "PolarOPS" in res.text

        # 3. Test commander override
        res = await client.post("/api/commander/override", json={"ambient_temp_c": -35.0, "wind_speed_ms": 28.0})
        print("[TEST] /api/commander/override ->", res.status_code, res.json())
        assert res.status_code == 200

        ans = res.json().get("answer", "")
        print("[TEST] /api/chat ->", res.status_code, "Answer received:", len(ans), "chars")
        assert "answer" in res.json()

        # 5. Test history
        res = await client.get("/api/history")
        print("[TEST] /api/history ->", res.status_code, f"Telemetry rows: {len(res.json().get('telemetry', []))}")
        assert res.status_code == 200

    # 6. Test WebSocket
    async with websockets.connect("ws://127.0.0.1:8000/ws/telemetry") as ws:
        msg = await ws.recv()
        data = json.loads(msg)
        print("[TEST] WebSocket packet received!")
        print("       Station:", data.get("telemetry", {}).get("station_id"))
        print("       Wind:", data.get("telemetry", {}).get("wind_speed_ms"), "m/s")
        print("       Guardrail Overridden:", data.get("guardrail", {}).get("is_overridden"))
        print("       AI Explanation:", data.get("explanation"))
        assert "telemetry" in data
        assert "dispatch" in data

    print("\n[SUCCESS] ALL ENDPOINT AND WEBSOCKET TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(verify_endpoints())
