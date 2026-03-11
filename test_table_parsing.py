import pandas as pd  # pyre-ignore
import os
from logic_parsing import process_table_file  # pyre-ignore

def test_table_parsing():
    print("--- Running Table Parsing Verification ---")
    
    # 1. Create a synthetic CSV with non-standard headers
    csv_content = """V_cell,i_cell,Ah_cap,Cyc,Step_Index
3.5,0.1,0.01,1,1
3.6,0.1,0.02,1,1
3.7,0.1,0.03,1,1
"""
    csv_path = "test_sample.csv"
    with open(csv_path, "w") as f:
        f.write(csv_content)
        
    try:
        # 2. Process the file
        cell_label = "Test_Table_Cell"
        mass_mg = 10.0
        mass_g = mass_mg / 1000.0
        theoretical_cap = 170.0
        
        df = process_table_file(csv_path, cell_label, mass_g, theoretical_cap)
        
        print(f"Mapped Columns: {df.columns.tolist()}")
        
        # 3. Assertions
        assert 'Voltage (V)' in df.columns
        assert 'Current (mA)' in df.columns
        assert 'Capacity (mAh)' in df.columns
        assert 'Cycle Index' in df.columns
        assert 'Step' in df.columns
        
        # Check normalization (Ah to mAh)
        # 0.01 Ah should becomes 10 mAh
        print(f"Capacity Sample: {df['Capacity (mAh)'].iloc[0]}")
        assert df['Capacity (mAh)'].iloc[0] == 10.0
        
        # Check current (Amps to mA)
        # 0.1 Amps should become 100 mA
        print(f"Current Sample: {df['Current (mA)'].iloc[0]}")
        assert df['Current (mA)'].iloc[0] == 100.0
        
        print("--- Table Parsing Verification Passed! ---")
        
    finally:
        if os.path.exists(csv_path):
            os.remove(csv_path)

if __name__ == "__main__":
    test_table_parsing()
