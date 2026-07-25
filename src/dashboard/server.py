"""
Read-only Dashboard HTTP server implementation.
Implements SR-5, FR-12, FR-13, and 12_API_Design.md §4.
Strictly read-only: HTTP POST/PUT/DELETE return 405 Method Not Allowed.
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import urllib.parse
from typing import Any, Optional, Dict
from src.shared.logging import get_logger
from src.storage.queries import get_decision_trace
from src.analytics.kpi import generate_kpi_report, compare_runs

logger = get_logger("dashboard.server")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Eco-Loop Building Agents Dashboard</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
        h1 { color: #38bdf8; border-bottom: 2px solid #1e293b; padding-bottom: 10px; }
        .card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-top: 20px; }
        .card { background: #1e293b; border-radius: 8px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
        .card h3 { margin-top: 0; color: #94a3b8; font-size: 0.9rem; text-transform: uppercase; }
        .metric { font-size: 2rem; font-weight: bold; color: #f8fafc; }
        .status-badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-weight: bold; background: #22c55e; color: #052e16; }
        .status-degraded { background: #ef4444; color: #450a0a; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { text-align: left; padding: 10px; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; font-weight: 600; }
    </style>
</head>
<body>
    <h1>Eco-Loop Building Control Monitor</h1>
    <div class="card-grid">
        <div class="card">
            <h3>System Status</h3>
            <div id="status-badge" class="status-badge">NOMINAL</div>
            <p id="mode-desc">Mode: Agent Driven</p>
        </div>
        <div class="card">
            <h3>Total Energy Consumed</h3>
            <div class="metric" id="energy-val">-- kWh</div>
        </div>
        <div class="card">
            <h3>PMV Band Compliance</h3>
            <div class="metric" id="comfort-val">-- %</div>
        </div>
        <div class="card">
            <h3>Fallback Rate</h3>
            <div class="metric" id="fallback-val">-- %</div>
        </div>
    </div>
</body>
</html>
"""


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP Request Handler enforcing read-only REST API endpoints.
    Rejecting non-GET requests with 405 Method Not Allowed (SR-5).
    """

    db_conn: Any = None
    active_run_id: str = "run_default"
    baseline_run_id: Optional[str] = None
    health_monitor: Any = None

    def do_POST(self):
        self.send_error(405, "Method Not Allowed: Dashboard is strictly read-only (SR-5)")

    def do_PUT(self):
        self.send_error(405, "Method Not Allowed: Dashboard is strictly read-only (SR-5)")

    def do_DELETE(self):
        self.send_error(405, "Method Not Allowed: Dashboard is strictly read-only (SR-5)")

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in ("/", "/index.html", "/demo"):
            try:
                with open("src/dashboard/demo_visualizer.html", "r", encoding="utf-8") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
                return
            except Exception:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
                return

        if path == "/api/status":
            health_info = (
                self.health_monitor.get_health_status()
                if self.health_monitor
                else {"status": "nominal", "degraded_mode_active": False}
            )
            data = {
                "active_run_id": self.active_run_id,
                "status": health_info.get("status", "nominal"),
                "degraded_mode": health_info.get("degraded_mode_active", False),
            }
            self._send_json(data)
            return

        if path == "/api/kpi":
            if self.db_conn:
                kpi = generate_kpi_report(self.db_conn, self.active_run_id)
            else:
                kpi = {"run_id": self.active_run_id, "total_kwh": 0.0, "pmv_compliance_pct": 100.0, "fallback_rate_pct": 0.0}
            self._send_json(kpi)
            return

        if path.startswith("/api/trace/"):
            cycle_id = path.split("/api/trace/")[1]
            if self.db_conn:
                trace = get_decision_trace(self.db_conn, cycle_id)
                if trace:
                    self._send_json(trace)
                    return
            self.send_error(404, f"Trace for cycle_id '{cycle_id}' not found")
            return

        if path == "/api/comparison":
            if self.db_conn and self.baseline_run_id:
                comp = compare_runs(self.db_conn, self.baseline_run_id, self.active_run_id)
                self._send_json(comp)
            else:
                self._send_json({"error": "No baseline run available for comparison"})
            return

        self.send_error(404, "Not Found")

    def _send_json(self, data: Dict[str, Any], status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, format, *args):
        pass


class DashboardServer:
    """
    Read-only HTTP dashboard server manager.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        db_conn: Any = None,
        active_run_id: str = "run_default",
        health_monitor: Any = None,
    ):
        self.host = host
        self.port = port
        self.db_conn = db_conn
        self.active_run_id = active_run_id
        self.health_monitor = health_monitor

        DashboardRequestHandler.db_conn = db_conn
        DashboardRequestHandler.active_run_id = active_run_id
        DashboardRequestHandler.health_monitor = health_monitor

        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts dashboard HTTP server in a background thread."""
        try:
            self._server = HTTPServer((self.host, self.port), DashboardRequestHandler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="DashboardServer")
            self._thread.start()
            logger.info(f"Dashboard HTTP server running at http://{self.host}:{self.port} (Read-Only)")
        except Exception as e:
            logger.error(f"Failed to start Dashboard server on port {self.port}: {e}")

    def stop(self) -> None:
        """Stops the dashboard server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("Dashboard server stopped.")
