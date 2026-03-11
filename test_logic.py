import pandas as pd
import numpy as np
from logic_electrochem import calculate_dqdv, calculate_metrics, map_crate

def test_math_logic():
    print("--- Running Electrochemical Logic Smoke Test ---")
    
    # Synthetic data: 1 cycle, linear capacity, sine voltage
    n_points = 100
    df = pd.DataFrame({
        'Cell_Name': ['Test_Cell'] * n_points,
        'Cycle Index': [1] * n_points,
        'Step': [1] * n_points,
        'Step_Type': ['Charge'] * (n_points // 2) + ['Discharge'] * (n_points // 2),
        'Capacity (mAh)': np.linspace(0, 10, n_points),
        'Voltage (V)': 3.0 + 1.0 * np.sin(np.linspace(0, np.pi, n_points)),
        'Current (mA)': [10] * n_points
    })
    
    mass_g = 0.010 # Specific cap should be Capacity / mass_g
    theoretical_cap = 170.0
    
    # 1. Test Metrics (Specific Capacity, CE)
    df = calculate_metrics(df, mass_g)
    print(f"Max Specific Capacity: {df['Specific Cap. (mAh/g)'].max():.2f} mAh/g")
    assert 'Specific Cap. (mAh/g)' in df.columns
    assert df['Specific Cap. (mAh/g)'].max() > 0
    
    # 2. Test C-Rate
    df = map_crate(df, theoretical_cap, mass_g)
    print(f"Calculated C-Rate: {df['C_Rate'].iloc[0]:.4f}C")
    assert 'C_Rate' in df.columns
    
    # 3. Test dQ/dV
    df = calculate_dqdv(df, window_size=5)
    print(f"dQ/dV head:\n{df['dQ_dV'].dropna().head()}")
    assert 'dQ_dV' in df.columns
    
    print("--- Smoke Test Passed! ---")

if __name__ == "__main__":
    test_math_logic()
