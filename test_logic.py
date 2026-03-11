import pandas as pd
import numpy as np
from logic_electrochem import calculate_dqdv, calculate_metrics, map_crate

def test_math_logic():
    print("--- Running Electrochemical Logic Smoke Test ---")
    
    # Synthetic data: 1 cycle, linear capacity, sine voltage
    n_points = 100
    df = pd.DataFrame({
        'Cell_Name': ['Test_Cell'] * n_points,
        'Cycle': [1] * n_points,
        'Step': [1] * n_points,
        'Step_Type': ['Charge'] * (n_points // 2) + ['Discharge'] * (n_points // 2),
        'Capacity_mAh': np.linspace(0, 10, n_points),
        'Voltage_V': 3.0 + 1.0 * np.sin(np.linspace(0, np.pi, n_points)),
        'Current_mA': [10] * n_points
    })
    
    mass_mg = 10.0
    theoretical_cap = 170.0
    
    # 1. Test Metrics (Specific Capacity, CE)
    df = calculate_metrics(df, mass_mg)
    print(f"Max Specific Capacity: {df['Specific_Capacity_mAh_g'].max():.2f} mAh/g")
    assert 'Specific_Capacity_mAh_g' in df.columns
    assert df['Specific_Capacity_mAh_g'].max() > 0
    
    # 2. Test C-Rate
    df = map_crate(df, theoretical_cap, mass_mg)
    print(f"Calculated C-Rate: {df['C_Rate'].iloc[0]:.4f}C")
    assert 'C_Rate' in df.columns
    
    # 3. Test dQ/dV
    df = calculate_dqdv(df, window_size=5)
    print(f"dQ/dV head:\n{df['dQ_dV'].dropna().head()}")
    assert 'dQ_dV' in df.columns
    
    print("--- Smoke Test Passed! ---")

if __name__ == "__main__":
    test_math_logic()
