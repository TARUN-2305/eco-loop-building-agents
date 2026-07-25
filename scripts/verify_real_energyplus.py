"""
Verification script for official NREL EnergyPlus C++ Runtime Engine.
"""

import sys
import os

# Add official NREL EnergyPlus C++ library directory to Python path
ep_path = r"C:\EnergyPlusV26-1-0\EnergyPlus-26.1.0-6f2e40d102-Windows-x86_64"
if ep_path not in sys.path:
    sys.path.insert(0, ep_path)

import pyenergyplus
from pyenergyplus.api import EnergyPlusAPI

print("=========================================================")
print("NREL EnergyPlus C++ Runtime API Verification")
print("=========================================================")

api = EnergyPlusAPI()
state = api.state_manager.new_state()

idf_abs = os.path.abspath("data/idf/baseline.idf")
epw_abs = os.path.abspath("data/epw/USA_CA_San.Francisco.Intl.AP.724940_TMY3.epw")

print(f"Target IDF: {idf_abs} (Exists: {os.path.exists(idf_abs)})")
print(f"Target EPW: {epw_abs} (Exists: {os.path.exists(epw_abs)})")

# Register callback
cb_fired = False

def zone_cb(s):
    global cb_fired
    cb_fired = True

api.runtime.callback_end_zone_timestep_after_zone_reporting(state, zone_cb)

print("Invoking real NREL C++ EnergyPlus engine via API...")
args = ["-d", "out_verify", "-w", epw_abs, idf_abs]
exit_code = api.runtime.run_energyplus(state, args)

print("=========================================================")
print(f"NREL C++ EnergyPlus Exit Code: {exit_code}")
print(f"Callback Fired: {cb_fired}")
print("=========================================================")

api.state_manager.delete_state(state)
