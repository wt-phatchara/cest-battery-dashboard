import pandas as pd  # pyre-ignore
import NewareNDA     # pyre-ignore
import os
import shutil
import uuid
import tempfile
import logging
# ctypes is only for Windows short-path support

# Trace which file is being loaded
print(f"!!! VERSION 8.0 !!! Loading logic_parsing from: {__file__}")

# --- MONKEY PATCH NEWARENDA ---
# Only attempt if the dicts and multiplier_dict exist to prevent startup crashes.
try:
    if hasattr(NewareNDA, 'dicts') and hasattr(NewareNDA.dicts, 'multiplier_dict'):
        if 3000 not in NewareNDA.dicts.multiplier_dict:
            NewareNDA.dicts.multiplier_dict[3000] = 1e-2
            print("!!! DEBUG !!! Successfully monkey-patched NewareNDA 3000 multiplier.")
except Exception as e:
    print(f"!!! DEBUG !!! Patch warning: {e}")
# ------------------------------

# GLOBAL OVERRIDE: Skip environment overrides on Linux (Streamlit Cloud handles /tmp better)
if os.name == 'nt':
    SAFE_BASE = "C:\\ndax_temp" # Use root-dir on Windows to avoid space issues
    try:
        os.makedirs(SAFE_BASE, exist_ok=True)
        os.environ['TEMP'] = SAFE_BASE
        os.environ['TMP'] = SAFE_BASE
        tempfile.tempdir = SAFE_BASE
    except Exception as e:
        print(f"!!! DEBUG !!! Windows Temp Override Warning: {e}")

def get_short_path_name(long_name: str) -> str:
    """
    Gets the short path name of a file system path to bypass Windows space issues.
    """
    if os.name != 'nt':
        return long_name
    import ctypes
    try:
        output_buf_size = 0
        max_tries = 100
        for _ in range(max_tries):
            output_buf = ctypes.create_unicode_buffer(output_buf_size)
            needed = ctypes.windll.kernel32.GetShortPathNameW(long_name, output_buf, output_buf_size) # type: ignore
            if needed == 0:
                return long_name
            if output_buf_size >= needed:
                return output_buf.value
            output_buf_size = needed
        return long_name
    except Exception:
        return long_name

def process_nda_file(file_path, cell_label, mass_g, theoretical_capacity):
    """
    Reads a .nda or .ndax file, extracts data, and performs initial cleaning.
    """
    # Move the file to the system temp directory to avoid "New folder" space issues.
    # NewareNDA's internal extraction (which creates .ndc files) often chokes on 
    # input paths containing spaces or long character sequences on Windows.
    abs_path = os.path.abspath(file_path)
    extension = os.path.splitext(abs_path)[1].lower()
    
    # Use a short local folder in the project directory
    project_dir = os.path.dirname(os.path.abspath(__file__))
    sys_temp = os.path.join(project_dir, "data_temp")
    os.makedirs(sys_temp, exist_ok=True)
    
    # CRITICAL: Normalize to DOS 8.3 Short Path to remove ALL spaces
    sys_temp = get_short_path_name(sys_temp)
        
    unique_hex = str(uuid.uuid4().hex)
    unique_id = unique_hex[0:8]  # pyre-ignore
    safe_path = os.path.abspath(os.path.join(sys_temp, f"bat_{unique_id}{extension}"))
    safe_path = get_short_path_name(safe_path)
    
    try:
        shutil.copy2(abs_path, safe_path)
        
        # Check if the file is a valid ZIP (ndax files are zips)
        if extension == '.ndax':
            import zipfile
            if not zipfile.is_zipfile(safe_path):
                raise ValueError(f"The file {cell_label} is not a valid .ndax (ZIP) file.")

        print(f"!!! DEBUG v5.0 !!! Attempting to read: {safe_path}")
        print(f"!!! DEBUG v5.0 !!! File exists: {os.path.exists(safe_path)}")
        print(f"!!! DEBUG v5.0 !!! Process TEMP: {os.environ.get('TEMP')}")
        
        # Parse from the clean system temp path
        df = NewareNDA.read(safe_path)
    except Exception as e:
        import traceback
        err_msg = str(e)
        raise Exception(f"Failed to parse {cell_label}. Original Error:\n{traceback.format_exc()}")
    finally:
        # Cleanup the safe temp file AND any extracted internal files (.ndc)
        try:
            for f in os.listdir(sys_temp):
                if f.startswith(f"bat_parse_{unique_id}"):
                    try:
                        os.remove(os.path.join(sys_temp, f))
                    except Exception:
                        pass
        except Exception:
            pass 

    # Standardize column names (mapping NewareNDA output to our internal naming)
    # NewareNDA outputs different column names depending on file version:
    # E.g., 'Current(A)' vs 'Current(mA)', 'Charge_Capacity(mAh)' vs 'Capacity(Ah)'
    # We will normalize to: ['Timestamp', 'Step', 'Cycle Index', 'Step_Type', 'Current (mA)', 'Voltage (V)', 'Capacity (mAh)', 'Cell_Name']
    
    # 1. Base Renaming Mapping
    # Prevent 2D DataFrames: NewareNDA sometimes outputs BOTH 'Step' and 'Step_Index'.
    # If we rename 'Step_Index' to 'Step' when 'Step' already exists, we get duplicate columns.
    cols_to_drop = []
    if 'Step_Index' in df.columns and 'Step' in df.columns:
        cols_to_drop.append('Step')
    if 'Cycle_Index' in df.columns and 'Cycle' in df.columns:
        cols_to_drop.append('Cycle')
    if cols_to_drop:
        df.drop(columns=cols_to_drop, inplace=True)

    rename_dict = {
        'Step_Index': 'Step',
        'Cycle_Index': 'Cycle Index',
        'Cycle': 'Cycle Index'
    }
    df.rename(columns=rename_dict, inplace=True)
    
    # Ensure 'Step_Type' exists or fallback to 'Status' if that's what NewareNDA provided
    if 'Step_Type' not in df.columns and 'Status' in df.columns:
        df.rename(columns={'Status': 'Step_Type'}, inplace=True)

    # 2. Dynamic Unit Conversions
    # Voltage
    if 'Voltage(V)' in df.columns:
        df['Voltage (V)'] = df['Voltage(V)']
    elif 'Voltage' in df.columns:
         df['Voltage (V)'] = df['Voltage']

    # Current (Normalize to mA)
    if 'Current(A)' in df.columns:
        df['Current (mA)'] = df['Current(A)'] * 1000.0
    elif 'Current(mA)' in df.columns:
        df['Current (mA)'] = df['Current(mA)']
        
    # Capacity (Normalize to mAh)
    # Some internal formats output a single Capacity column, others split it into Charge/Discharge
    if 'Capacity(Ah)' in df.columns:
        df['Capacity (mAh)'] = df['Capacity(Ah)'] * 1000.0
    elif 'Capacity(mAh)' in df.columns:
        df['Capacity (mAh)'] = df['Capacity(mAh)']
    elif 'Charge_Capacity(mAh)' in df.columns and 'Discharge_Capacity(mAh)' in df.columns:
        # If separated, we can synthesize a single gross capacity column for plotting 
        # (or just keep them separated depending on downstream logic, but app.py expects Capacity (mAh) initially)
        # We'll map the max of the two since typically only one is active per step
        df['Capacity (mAh)'] = df[['Charge_Capacity(mAh)', 'Discharge_Capacity(mAh)']].max(axis=1)
    elif 'Charge_capacity' in df.columns and 'Discharge_capacity' in df.columns:
        df['Capacity (mAh)'] = df[['Charge_capacity', 'Discharge_capacity']].max(axis=1)
        
    # Energy (Normalize to mWh)
    if 'Energy(Wh)' in df.columns:
        df['Energy (mWh)'] = df['Energy(Wh)'] * 1000.0
    elif 'Energy(mWh)' in df.columns:
        df['Energy (mWh)'] = df['Energy(mWh)']
    elif 'Charge_Energy(mWh)' in df.columns and 'Discharge_Energy(mWh)' in df.columns:
         df['Energy (mWh)'] = df[['Charge_Energy(mWh)', 'Discharge_Energy(mWh)']].max(axis=1)

    # Normalize Step_Type for math logic (Charge/Discharge)
    # Neware types: 'CC_Chg', 'CC_DChg', 'CCCV_Chg', 'Rest', etc.
    if 'Step_Type' in df.columns:
        df['Step_Type'] = df['Step_Type'].astype(str).fillna('Other')
        df.loc[df['Step_Type'].str.contains('Chg', case=False, na=False), 'Step_Type'] = 'Charge'
        df.loc[df['Step_Type'].str.contains('Dchg', case=False, na=False), 'Step_Type'] = 'Discharge'
    else:
        df['Step_Type'] = 'Other'
    
    # Metadata tagging
    df['Cell_Name'] = cell_label
    df['Mass_g'] = mass_g
    df['Theoretical_Capacity_mAh_g'] = theoretical_capacity
    
    return df

def standardize_columns(df):
    """
    Attempts to map various column naming conventions to our internal standard.
    Standard: ['Voltage (V)', 'Current (mA)', 'Capacity (mAh)', 'Step', 'Cycle Index', 'Step_Type', 'Time']
    """
    mapping = {
        'Voltage (V)': [r'volt', r'^v$', r'v_cell'],
        'Current (mA)': [r'curr', r'^i$', r'i_cell', r'amp'],
        'Capacity (mAh)': [r'cap', r'^q$', r'ah', r'mah'],
        'Step': [r'step', r'status', r'state'],
        'Cycle Index': [r'cyc', r'index'],
        'Time': [r'time', r't_s', r'timestamp']
    }
    
    found_cols = {}
    remaining_cols = list(df.columns)
    
    import re
    for std_name, patterns in mapping.items():
        for p in patterns:
            for col in remaining_cols:
                if re.search(p, str(col), re.IGNORECASE):
                    found_cols[col] = std_name
                    remaining_cols.remove(col)
                    break
            if std_name in found_cols.values(): break
            
    df.rename(columns=found_cols, inplace=True)
    
    # Unit Normalization (Rough heuristics)
    if 'Voltage (V)' in df.columns:
        # If mean voltage is > 1000, it's likely mV
        if df['Voltage (V)'].mean() > 100:
            df['Voltage (V)'] = df['Voltage (V)'] / 1000.0
            
    if 'Current (mA)' in df.columns:
        # If values are extremely small, they might be Amps
        if df['Current (mA)'].abs().max() < 1:
            df['Current (mA)'] = df['Current (mA)'] * 1000.0

    if 'Capacity (mAh)' in df.columns:
        # If max cap is very small, might be Ah
        if df['Capacity (mAh)'].max() < 0.5:
             df['Capacity (mAh)'] = df['Capacity (mAh)'] * 1000.0

    if 'Step_Type' not in df.columns and 'Step' in df.columns:
        # Infer Charge/Discharge from Current if not provided
        df['Step_Type'] = 'Rest'
        if 'Current (mA)' in df.columns:
            df.loc[df['Current (mA)'] > 0.01, 'Step_Type'] = 'Charge'
            df.loc[df['Current (mA)'] < -0.01, 'Step_Type'] = 'Discharge'

    # Fallback for missing mandatory columns
    if 'Cycle Index' not in df.columns: df['Cycle Index'] = 1
    if 'Step' not in df.columns: df['Step'] = 1
    
    return df

def process_table_file(file_path, cell_label, mass_g, theoretical_capacity):
    """
    Reads a .csv or .xlsx file and standardizes it to our internal format.
    """
    extension = os.path.splitext(file_path)[1].lower()
    
    if extension == '.csv':
        df = pd.read_csv(file_path)
    else:
        # Support both .xls and .xlsx
        df = pd.read_excel(file_path)
        
    df = standardize_columns(df)
    
    # Metadata tagging
    df['Cell_Name'] = cell_label
    df['Mass_g'] = mass_g
    df['Theoretical_Capacity_mAh_g'] = theoretical_capacity
    
    return df

def clean_data(df):
    """
    General data cleaning: handles messy hardware noise.
    """
    # Remove NaN values in critical columns
    critical_cols = ['Voltage (V)', 'Cycle Index', 'Step']
    df = df.dropna(subset=critical_cols)
    
    # Ensure types are correct
    df['Cycle Index'] = df['Cycle Index'].astype(int)
    df['Step'] = df['Step'].astype(int)
    
    return df
