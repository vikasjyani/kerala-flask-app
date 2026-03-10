
import sys
import os

# Add the project root to the python path
sys.path.append(os.getcwd())

from commercial_cooking import calculate_consumption_based
from database.db_helper import DatabaseHelper

# Mock form data class
class MockForm(dict):
    def getlist(self, key):
        val = self.get(key)
        if isinstance(val, list):
            return val
        return [val] if val else []

# Mock data
data = MockForm({
    'primary_fuel': 'LPG',
    'lpg_types': ['Domestic', 'Commercial'],
    'domestic_cylinders': 1,
    'commercial_cylinders': 1,
    'commercial_cylinder_price': 0, 
})
institution_data = {
    'servings_per_day': 100,
    'working_days': 25,
    'district': 'New Delhi', # Example district, though DB might only have Keralam districts, we check if it runs
    'institution_type': 'School'
}
kitchen_data = {}
institution_id = 1

def verify_fix():
    print("Running calculate_consumption_based with LPG...", flush=True)
    try:
        result = calculate_consumption_based(data, institution_data, kitchen_data, institution_id)
        print(f"Full Result: {result}", flush=True)
        
        if 'error' in result:
             print(f"Function returned error: {result['error']}", flush=True)

        # Check if we got results and didnt crash
        lpg_details = result['fuel_details']['LPG']
        print("SUCCESS! Result obtained.", flush=True)
        print(f"Monthly Cost: {lpg_details['monthly_cost']}", flush=True)
        print(f"Domestic Price used seems valid: {lpg_details['monthly_cost'] > 0}", flush=True)
        
    except Exception as e:
        print(f"FAILED with error: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_fix()
