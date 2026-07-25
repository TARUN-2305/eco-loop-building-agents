import sys
import os

sys.path.append(r"C:\EnergyPlusV26-1-0\EnergyPlus-26.1.0-6f2e40d102-Windows-x86_64")
import pyenergyplus
from pyenergyplus.api import EnergyPlusAPI

api = EnergyPlusAPI()
state = api.state_manager.new_state()

idf = os.path.abspath("data/idf/baseline.idf")
epw = os.path.abspath("data/epw/USA_CA_San.Francisco.Intl.AP.724940_TMY3.epw")

api.exchange.request_variable(state, "Zone Mean Air Temperature", "SPACE1-1")

def cb(s):
    print("=== Testing Actuator Handles ===")
    comps = ["Schedule:Compact", "Schedule:Constant", "Schedule", "Zone Temperature Control"]
    ctrls = ["Schedule Value", "Heating Setpoint Schedule Value", "Cooling Setpoint Schedule Value"]
    keys = ["HTGSETP_SCH", "CLGSETP_SCH"]
    
    for k in keys:
        for c in comps:
            for ctrl in ctrls:
                h = api.exchange.get_actuator_handle(s, c, ctrl, k)
                if h != -1:
                    print(f"SUCCESS! Key: '{k}', Comp: '{c}', Ctrl: '{ctrl}' => Handle: {h}")
                else:
                    print(f"Failed: Key: '{k}', Comp: '{c}', Ctrl: '{ctrl}'")
    sys.exit(0)

api.runtime.callback_begin_zone_timestep_before_init_heat_balance(state, cb)
api.runtime.run_energyplus(state, ["-d", "out_test", "-w", epw, idf])
