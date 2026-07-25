"""
Unit tests for Dashboard HTTP server read-only API endpoints and 405 rejection of mutation methods (SR-5).
"""

import pytest
import requests
from src.dashboard.server import DashboardServer


@pytest.fixture
def dashboard_server():
    server = DashboardServer(host="127.0.0.1", port=8089, active_run_id="run_test_dash")
    server.start()
    yield "http://127.0.0.1:8089"
    server.stop()


def test_dashboard_get_status_and_kpi(dashboard_server):
    # GET /api/status
    resp_status = requests.get(f"{dashboard_server}/api/status")
    assert resp_status.status_code == 200
    data_status = resp_status.json()
    assert data_status["active_run_id"] == "run_test_dash"
    assert data_status["status"] == "nominal"

    # GET /api/kpi
    resp_kpi = requests.get(f"{dashboard_server}/api/kpi")
    assert resp_kpi.status_code == 200
    data_kpi = resp_kpi.json()
    assert "total_kwh" in data_kpi
    assert "pmv_compliance_pct" in data_kpi


def test_dashboard_rejects_post_put_delete_sr5(dashboard_server):
    # POST request -> 405 Method Not Allowed
    resp_post = requests.post(f"{dashboard_server}/api/status", json={"data": "test"})
    assert resp_post.status_code == 405

    # PUT request -> 405 Method Not Allowed
    resp_put = requests.put(f"{dashboard_server}/api/status", json={"data": "test"})
    assert resp_put.status_code == 405

    # DELETE request -> 405 Method Not Allowed
    resp_del = requests.delete(f"{dashboard_server}/api/status")
    assert resp_del.status_code == 405
