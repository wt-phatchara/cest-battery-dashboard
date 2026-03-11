import pandas as pd  # pyre-ignore
import numpy as np  # pyre-ignore
from scipy.signal import savgol_filter  # pyre-ignore

def standardize_phase(val):
    val_lower = str(val).lower()
    if 'dchg' in val_lower or 'discharge' in val_lower: return 'Discharge'
    if 'chg' in val_lower or 'charge' in val_lower: return 'Charge'
    return 'Rest'

def calculate_dqdv(df, window_size=15, polyorder=3):
    """
    Calculates the differential capacity (dQ/dV) using a Savitzky-Golay filter.
    Handles division by zero by clipping extreme values.
    """
    if window_size % 2 == 0:
        window_size += 1
        
    df['Phase'] = df['Step_Type'].apply(standardize_phase)
    # Sort by time to preserve exact electrochemical sequence
    if 'Time' in df.columns:
        df = df.sort_values(['Cell_Name', 'Time'])
    else:
        df = df.sort_values(['Cell_Name', 'Cycle Index', 'Step'])
        
    df['dQ_dV'] = np.nan
    
    # Calculate derivative independently for each continuous phase block to prevent connecting charge and discharge
    for (cell, cycle, phase), group in df.groupby(['Cell_Name', 'Cycle Index', 'Phase']):
        if phase == 'Rest' or len(group) < window_size: 
            continue
            
        group = group.copy()
        try:
            v_smooth = savgol_filter(group['Voltage (V)'], window_size, polyorder)
        except Exception:
            v_smooth = group['Voltage (V)'].values
            
        dq = group['Specific Cap. (mAh/g)'].diff().values
        dv = pd.Series(v_smooth).diff().values
        
        # Avoid zero division and massive spikes
        valid_mask = np.abs(dv) > 1e-4
        dqdv = np.zeros_like(dq)
        dqdv[valid_mask] = dq[valid_mask] / dv[valid_mask]
        
        # Apply strict bounds to match template view (e.g. typical ranges -10000 to 10000)
        dqdv = np.clip(dqdv, -20000, 20000)
        
        # Smooth the resulting derivative curve for presentation quality
        try:
            dqdv_smooth = savgol_filter(pd.Series(dqdv).fillna(0), window_size, 1)
        except Exception:
            dqdv_smooth = dqdv
            
        df.loc[group.index, 'dQ_dV'] = dqdv_smooth
        
    return df

def calculate_metrics(df, mass_g):
    """
    Normalizes capacity by mass and calculates Coulombic Efficiency (CE) and dV.
    """
    df['Specific Cap. (mAh/g)'] = df['Capacity (mAh)'] / mass_g
    df['Phase'] = df['Step_Type'].apply(standardize_phase)
    
    # Calculate CE per cycle: CE = (Discharge / Charge) * 100
    summary = df.groupby(['Cycle Index', 'Phase'])['Specific Cap. (mAh/g)'].max().unstack()
    
    if 'Charge' in summary.columns and 'Discharge' in summary.columns:
        summary['Coulombic Eff.'] = (summary['Discharge'] / summary['Charge']) * 100
    else:
        summary['Coulombic Eff.'] = np.nan
        
    # Calculate Energy Efficiency if Energy exists
    energy_col = next((col for col in df.columns if 'Energy (mWh)' in col or 'Energy' in col), None)
    if energy_col:
        eng_summary = df.groupby(['Cycle Index', 'Phase'])[energy_col].max().unstack()
        if 'Charge' in eng_summary.columns and 'Discharge' in eng_summary.columns:
            summary['Energy Eff.'] = (eng_summary['Discharge'] / eng_summary['Charge']) * 100
        else:
            summary['Energy Eff.'] = np.nan
    else:
        summary['Energy Eff.'] = np.nan
        
    # Calculate dV (Voltage Differential)
    avg_v = df.groupby(['Cycle Index', 'Phase'])['Voltage (V)'].mean().unstack()
    if 'Charge' in avg_v.columns and 'Discharge' in avg_v.columns:
        summary['dV'] = avg_v['Charge'] - avg_v['Discharge']
    else:
        summary['dV'] = np.nan
        
    # Merge CE, EE, dV back to main
    df = df.merge(summary[['Coulombic Eff.', 'Energy Eff.', 'dV']], on='Cycle Index', how='left')
    
    return df

def map_crate(df, theoretical_capacity_mah_g, mass_g):
    """
    Maps applied current to C-Rate based on theoretical capacity and active mass.
    """
    theoretical_capacity_ma = theoretical_capacity_mah_g * mass_g
    
    # C-Rate = Current (mA) / Theoretical Capacity (mA)
    df['C_Rate'] = df.groupby(['Cycle Index', 'Step'])['Current (mA)'].transform(lambda x: abs(x).mean()) / theoretical_capacity_ma
    
    return df
