import streamlit as st  # pyre-ignore
import pandas as pd  # pyre-ignore
import numpy as np  # pyre-ignore
import plotly.express as px  # pyre-ignore
import plotly.graph_objects as objects  # pyre-ignore
import os
import traceback
import uuid
from datetime import datetime
from logic_parsing import process_nda_file, clean_data  # pyre-ignore
from logic_electrochem import calculate_dqdv, calculate_metrics, map_crate  # pyre-ignore
import requests

# --- GitHub Integration (Phase 7: Self-Development Loop) ---
GITHUB_REPO = "wt-phatchara/cest-battery-dashboard"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")  # Add this to Streamlit Cloud Secrets

def create_gh_issue(title, body):
    if not GITHUB_TOKEN:
        return False
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"title": title, "body": body}
    response = requests.post(url, headers=headers, json=data)
    return response.status_code == 201

# --- UI Configuration & Styling ---
st.set_page_config(page_title="Battery Performance Auto-Plotter", layout="wide")
st.title("⚡ Scalable Battery Performance Auto-Plotter")
st.markdown("---")

# --- Constants & Paths ---
TEMP_DIR = os.path.abspath("data_temp")
FEEDBACK_FILE = os.path.abspath("feedback_log.txt")

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# --- Shared Plot Configuration ---
PLOT_CONFIG = {'toImageButtonOptions': {'format': 'svg', 'scale': 1}}

def apply_custom_theme(fig):
    """
    Applies the academic/publication plotting style extracted from user's training data.
    Thick black borders, no gridlines, inward ticks, bold readable fonts.
    """
    fig.update_layout(
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin={"l": 70, "r": 40, "t": 50, "b": 60},
        font={"family": "Arial, sans-serif", "size": 14, "color": "black"},
        title={"font": {"size": 18, "family": "Arial, sans-serif", "color": "black"}}
    )
    # Configure Axes
    axis_config = {
        "showgrid": False,
        "showline": True,
        "linewidth": 2.5,
        "linecolor": 'black',
        "mirror": True,
        "ticks": 'inside',
        "tickwidth": 2,
        "ticklen": 6,
        "tickcolor": 'black',
        "title_font": {"size": 16, "family": "Arial, sans-serif", "color": "black", "weight": "bold"}
    }
    fig.update_xaxes(**axis_config)
    fig.update_yaxes(**axis_config)
    
    # Configure Lines/Markers
    fig.update_traces(line={"width": 3})
    
    return fig

# --- Cached Processing Logic ---
@st.cache_data
def cached_process_file(file_bytes, file_name, cell_label, mass_mg, theoretical_cap):
    """
    Caches the parsing and math logic to avoid re-processing on every UI change.
    """
    import tempfile
    
    # 1. Ensure your local short-path temp directory exists
    temp_dir = os.path.join(os.getcwd(), "data_temp")
    os.makedirs(temp_dir, exist_ok=True)

    # 2. Force Streamlit to extract the .ndax inside this local folder
    with tempfile.NamedTemporaryFile(dir=temp_dir, delete=False, suffix=".ndax") as tmp:
        tmp.write(file_bytes)
        temp_path = tmp.name
        
    try:
        df = process_nda_file(temp_path, cell_label, mass_mg, theoretical_cap)
        df = clean_data(df)
        df = calculate_metrics(df, mass_mg)
        df = map_crate(df, theoretical_cap, mass_mg)
        return df
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# --- Sidebar: File Upload & Metadata ---
st.sidebar.markdown("**Built by P.W., CEST team**")
st.sidebar.header("📂 Data Ingestion")
uploaded_files = st.sidebar.file_uploader(
    "Upload .nda or .ndax files", 
    accept_multiple_files=True, 
    type=["nda", "ndax"]
)

all_data = []

if uploaded_files:
    st.sidebar.subheader("Metadata Injection")
    for uploaded_file in uploaded_files:
        with st.sidebar.expander(f"⚙️ {uploaded_file.name}"):
            # Use distinct keys for metadata inputs
            cell_label = st.text_input(f"Cell Label", value=uploaded_file.name.split('.')[0], key=f"label_{uploaded_file.name}")
            mass_g = st.number_input(f"Active Mass (g)", value=0.010, step=0.001, format="%.4f", key=f"mass_{uploaded_file.name}")
            theoretical_cap = st.number_input(f"Theoretical Capacity (mAh/g)", value=170.0, step=1.0, key=f"cap_{uploaded_file.name}")
            
            try:
                # Process file using cached function
                # Note: tobytes() ensures the buffer is hashable for caching
                df = cached_process_file(uploaded_file.getvalue(), uploaded_file.name, cell_label, mass_g, theoretical_cap)
                all_data.append(df)
                st.sidebar.success(f"✅ {uploaded_file.name} loaded")
            except Exception as e:
                st.error(f"Error parsing {uploaded_file.name}: {e}")
                with open(FEEDBACK_FILE, "a") as f:
                    f.write(f"[{datetime.now()}] ERROR: {uploaded_file.name}\n{traceback.format_exc()}\n")

# --- Global UI Filters ---
if all_data:
    master_df = pd.concat(all_data, ignore_index=True)
    
    st.sidebar.markdown("---")
    st.sidebar.header("🎯 Global Filters")
    cells = master_df['Cell_Name'].unique()
    selected_cells = st.sidebar.multiselect("Select Cells", cells, default=cells)
    
    cycle_min = int(master_df['Cycle'].min())
    cycle_max = int(master_df['Cycle'].max())
    cycle_range = st.sidebar.slider("Cycle Range Filter", cycle_min, cycle_max, (cycle_min, cycle_max))
    
    # Phase 5: Interactive click state
    if "selected_cycle" not in st.session_state:
        st.session_state.selected_cycle = ""
        
    def reset_cycle():
        st.session_state.selected_cycle = ""
        
    specific_cycles_input = st.sidebar.text_input("Plot Specific Cycles (e.g. 3, 105, 510) - overrides slider", value=str(st.session_state.selected_cycle), key="cycle_override_input")
    
    if st.session_state.selected_cycle != "":
        st.sidebar.button("Reset Interactive Filter", on_click=reset_cycle)
    
    # Pre-filter data for all plots
    if specific_cycles_input:
        try:
            custom_cycles = [int(c.strip()) for c in specific_cycles_input.split(',')]
            filtered_df = master_df[(master_df['Cell_Name'].isin(selected_cells)) & (master_df['Cycle'].isin(custom_cycles))].copy()
        except:
            filtered_df = master_df[(master_df['Cell_Name'].isin(selected_cells)) & (master_df['Cycle'].between(cycle_range[0], cycle_range[1]))].copy()
    else:
        filtered_df = master_df[(master_df['Cell_Name'].isin(selected_cells)) & (master_df['Cycle'].between(cycle_range[0], cycle_range[1]))].copy()
    
    # Create Cycle_Step to explicitly separate disjointed continuous plotting lines (fixes zig-zag)
    filtered_df['Cycle_Step'] = filtered_df['Cycle'].astype(str) + '_' + filtered_df['Step'].astype(str)
    
    # --- Global Plotting Labels ---
    label_map = {
        "Specific_Capacity_mAh_g": "Specific Capacity (mAh/g)",
        "Capacity_mAh": "Capacity (mAh)",
        "Voltage_V": "Voltage (V)",
        "Current_mA": "Current (mA)",
        "Cycle": "Cycle Number",
        "Step": "Step Number",
        "Time": "Time (s)",
        "Retention (%)": "Retention (%)",
        "CE": "Coulombic Efficiency (%)",
        "EE": "Energy Efficiency (%)",
        "dV": "Voltage Differential (V)"
    }

    # --- Main Tabs ---
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "X-Y Profiles", 
        "Cycle Metrics", 
        "dQ/dV Analysis", 
        "Rate Capability",
        "Raw Data",
        "AI Training Hub"
    ])

    with tab1:
        st.subheader("Dynamic Line Profiles")
        with st.form("tab1_form"):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                x_axis = st.selectbox("X-Axis", options=["Specific_Capacity_mAh_g", "Capacity_mAh", "Voltage_V", "Time", "Step"], index=0, key="tab1_x")
                y_axis = st.selectbox("Y-Axis", options=["Voltage_V", "Specific_Capacity_mAh_g", "Capacity_mAh", "Current_mA"], index=0, key="tab1_y")
            with col2:
                x_min = st.number_input("X-Axis Min", value=None, key="tab1_xmin")
                x_max = st.number_input("X-Axis Max", value=None, key="tab1_xmax")
            with col3:
                y_min = st.number_input("Y-Axis Min", value=None, key="tab1_ymin")
                y_max = st.number_input("Y-Axis Max", value=None, key="tab1_ymax")
            
            submitted1 = st.form_submit_button("Update Plot")
            
        # Filter out 'Rest' data so we don't plot idle horizontal drifts
        plot_df = filtered_df[filtered_df['Phase'] != 'Rest'].copy()
        
        fig = px.line(plot_df, x=x_axis, y=y_axis, 
                    color="Cell_Name", line_group="Cycle_Step", 
                    title=f"<b>{label_map.get(y_axis, y_axis)} vs. {label_map.get(x_axis, x_axis)}</b>",
                    template="plotly_white",
                    labels={x_axis: label_map.get(x_axis, x_axis), y_axis: label_map.get(y_axis, y_axis)})
        
        if x_min is not None or x_max is not None:
            fig.update_xaxes(range=[x_min, x_max])
        if y_min is not None or y_max is not None:
            fig.update_yaxes(range=[y_min, y_max])
            
        st.plotly_chart(apply_custom_theme(fig), width="stretch", config=PLOT_CONFIG)

    with tab2:
        st.subheader("Dynamic Cycle Metrics")
        with st.form("tab2_form"):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                cycle_x = st.selectbox("X-Axis", options=["Cycle", "Time"], index=0, key="tab2_x")
                cycle_y = st.selectbox("Y-Axis", options=["Retention (%)", "Coulombic Efficiency (%)", "Energy Efficiency (%)", "Specific Capacity (mAh/g)", "Capacity (mAh)", "Voltage Differential (V)"], index=0, key="tab2_y")
            with col2:
                x_min2 = st.number_input("X-Axis Min", value=None, key="tab2_xmin")
                x_max2 = st.number_input("X-Axis Max", value=None, key="tab2_xmax")
            with col3:
                y_min2 = st.number_input("Y-Axis Min", value=None, key="tab2_ymin")
                y_max2 = st.number_input("Y-Axis Max", value=None, key="tab2_ymax")
                
            submitted2 = st.form_submit_button("Update Plot")
        
        # Aggregate cycle data using mapped 'Discharge' phase
        cycle_df = filtered_df[filtered_df['Phase'] == 'Discharge'].groupby(['Cell_Name', 'Cycle']).agg({
            'Specific_Capacity_mAh_g': 'max',
            'Capacity_mAh': 'max',
            'CE': 'first',
            'EE': 'first',
            'dV': 'first',
            'Time': 'max'
        }).reset_index()
        
        # Must sort by cycle so Retention calculates accurately (nth / 1st * 100)
        cycle_df = cycle_df.sort_values(['Cell_Name', 'Cycle'])
        cycle_df['Retention (%)'] = cycle_df.groupby('Cell_Name')['Specific_Capacity_mAh_g'].transform(lambda x: (x / x.iloc[0]) * 100 if len(x) > 0 else np.nan)
        
        # Map nice string back to column name
        y_col_map = {
            "Retention (%)": "Retention (%)",
            "Coulombic Efficiency (%)": "CE",
            "Energy Efficiency (%)": "EE",
            "Specific Capacity (mAh/g)": "Specific_Capacity_mAh_g",
            "Capacity (mAh)": "Capacity_mAh",
            "Voltage Differential (V)": "dV"
        }
        y_col = y_col_map[cycle_y]
        
        fig = px.line(cycle_df, x=cycle_x, y=y_col, color="Cell_Name", 
                     markers=True, title=f"<b>{cycle_y} vs. {label_map.get(cycle_x, cycle_x)}</b>", template="plotly_white",
                     labels={y_col: cycle_y, cycle_x: label_map.get(cycle_x, cycle_x)})
        # Make cycle markers thicker for visibility
        fig.update_traces(marker={"size": 8})
        
        if x_min2 is not None or x_max2 is not None:
            fig.update_xaxes(range=[x_min2, x_max2])
        if y_min2 is not None or y_max2 is not None:
            fig.update_yaxes(range=[y_min2, y_max2])
            
        fig = apply_custom_theme(fig)
        
        # Capture clicks on the scatter plot
        event = st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, on_select="rerun", selection_mode="points")
        if event and event.get("selection", {}).get("points"):
            clicked_point = event["selection"]["points"][0]
            # If X-Axis is Cycle, grab the exact cycle number the user clicked
            if cycle_x == "Cycle":
                clicked_cycle = int(clicked_point["x"])
                if st.session_state.selected_cycle != str(clicked_cycle):
                    st.session_state.selected_cycle = str(clicked_cycle)
                    st.rerun()

    with tab3:
        st.subheader("Differential Capacity (dQ/dV)")
        with st.form("tab3_form"):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                dqdv_x = st.selectbox("X-Axis", options=["Voltage_V", "Specific_Capacity_mAh_g", "Capacity_mAh"], index=0, key="tab3_x")
                smoothing_window = st.slider("Smoothing Window (Savgol Filter)", 5, 51, 15, step=2)
            with col2:
                x_min3 = st.number_input("X-Axis Min", value=None, key="tab3_xmin")
                x_max3 = st.number_input("X-Axis Max", value=None, key="tab3_xmax")
            with col3:
                y_min3 = st.number_input("Y-Axis Min", value=None, key="tab3_ymin")
                y_max3 = st.number_input("Y-Axis Max", value=None, key="tab3_ymax")
                
            submitted3 = st.form_submit_button("Update Plot")
            
        dqdv_list = []
        for cell in selected_cells:
            cell_df = filtered_df[filtered_df['Cell_Name'] == cell].copy()
            if not cell_df.empty:
                processed_cell_df = calculate_dqdv(cell_df, window_size=smoothing_window)
                dqdv_list.append(processed_cell_df)
        
        if dqdv_list:
            dqdv_df = pd.concat(dqdv_list)
            dqdv_df['Cycle_Step'] = dqdv_df['Cycle'].astype(str) + '_' + dqdv_df['Step'].astype(str)
            fig = px.line(dqdv_df, x=dqdv_x, y="dQ_dV", color="Cell_Name", 
                         line_group="Cycle_Step", title=f"<b>dQ/dV vs. {label_map.get(dqdv_x, dqdv_x)}</b>",
                         template="plotly_white",
                         labels={"dQ_dV": "dQ/dV", dqdv_x: label_map.get(dqdv_x, dqdv_x)})
            
            # Smart Default Crop for Outliers (if bounds not specifically set) - highly constrained based on generic template bounds
            y_range = [-15000, 15000]
            if y_min3 is not None:
                y_range[0] = y_min3
            if y_max3 is not None:
                y_range[1] = y_max3
            fig.update_yaxes(range=y_range)
            
            if x_min3 is not None or x_max3 is not None:
                fig.update_xaxes(range=[x_min3, x_max3])
                
            st.plotly_chart(apply_custom_theme(fig), width="stretch", config=PLOT_CONFIG)
        else:
            st.warning("No data available for dQ/dV calculation.")

    with tab4:
        st.subheader("Rate Capability")
        with st.form("tab4_form"):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                rate_metric = st.selectbox("Capacity Metric", ["Specific_Capacity_mAh_g", "Capacity_mAh"], index=0, key="tab4_metric")
            with col2:
                x_min4 = st.number_input("X-Axis Min", value=None, key="tab4_xmin")
                x_max4 = st.number_input("X-Axis Max", value=None, key="tab4_xmax")
            with col3:
                y_min4 = st.number_input("Y-Axis Min", value=None, key="tab4_ymin")
                y_max4 = st.number_input("Y-Axis Max", value=None, key="tab4_ymax")
                
            submitted4 = st.form_submit_button("Update Plot")
            
        rate_df = filtered_df[filtered_df['Phase'] == 'Discharge'].groupby(['Cell_Name', 'C_Rate', 'Cycle'])[rate_metric].max().reset_index()
        fig = px.scatter(rate_df, x="Cycle", y=rate_metric, color="Cell_Name", 
                        size_max=10, title="<b>Rate Capability Analysis</b>", template="plotly_white",
                        labels={rate_metric: label_map.get(rate_metric, rate_metric)})
        fig.update_traces(marker={"size": 12, "symbol": "circle"}) # Make markers prominent like in training data
        
        if x_min4 is not None or x_max4 is not None:
            fig.update_xaxes(range=[x_min4, x_max4])
        if y_min4 is not None or y_max4 is not None:
            fig.update_yaxes(range=[y_min4, y_max4])
            
        fig = apply_custom_theme(fig)
        
        # Capture clicks on the scatter plot
        event4 = st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, on_select="rerun", selection_mode="points")
        if event4 and event4.get("selection", {}).get("points"):
            clicked_point = event4["selection"]["points"][0]
            clicked_cycle = int(clicked_point["x"])
            if st.session_state.selected_cycle != str(clicked_cycle):
                st.session_state.selected_cycle = str(clicked_cycle)
                st.rerun()
        
    with tab5:
        st.subheader("Raw Extracted Data")
        st.caption("Showing limited preview of 1000 rows to prevent browser crash. Use Export below for full data.")
        st.dataframe(filtered_df.head(1000), width="stretch", height=400)

    with tab6:
        st.subheader("🤖 Local LLM AI Integration & Training Hub")
        st.markdown("Use this hub to train the Agent. Provide explicit prompts, directives, or upload pristine Plot Templates your team expects the software to mimic.")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown("#### ⚙️ Local LLM Connection")
            # Defaulting to your PC's Network IP so team members don't have to type it
            llm_url = st.text_input("Ollama API URL / EndPoint", value="http://192.168.68.112:11434")
            llm_model = st.selectbox("Select Target Model", ["qwen", "deepseek-coder", "llama3"])
            
            if st.button("Test Agent Connection"):
                if create_gh_issue("🔄 Connection Test", f"Triggered by {datetime.now()}. If you see this, the GitHub Token is working!"):
                    st.success("Test Issue created on GitHub! If your local optimizer is running, it should pick this up in ~5 mins.")
                else:
                    st.error("Failed to create Test Issue. Please check your GITHUB_TOKEN in Streamlit Secrets.")
            
            st.markdown("#### 🖼️ Template Injection")
            template_upload = st.file_uploader("Upload Target Plot Style (PNG/JPG/XLSX)", type=["png", "jpg", "jpeg", "xlsx"])
            if template_upload:
                if template_upload.name.endswith('.png') or template_upload.name.endswith('.jpg'):
                    st.image(template_upload, caption="Target Style Reference", width="stretch")
                else:
                    st.success(f"File {template_upload.name} buffered.")
                
        with col2:
            st.markdown("#### 💬 Prompt Sandbox")
            st.caption("Directives sent here are permanently burned into the Agent's working memory for the next build cycle.")
            
            if "prompt_history" not in st.session_state:
                st.session_state.prompt_history = []
            
            # Show conversation
            for msg in st.session_state.prompt_history:
                with st.chat_message("user"):
                    st.write(msg)
                    
            if prompt := st.chat_input("E.g. 'Please change the default gridlines to be dashed instead of solid across all plots.'"):
                st.session_state.prompt_history.append(prompt)
                
                bundle_log = f"[{datetime.now()}] LOCAL LLM DIRECTIVE (Model={llm_model}, URL={llm_url}): {prompt}\n"
                
                if template_upload:
                    train_dir = os.path.join(os.getcwd(), "Battery_Training_Data")
                    os.makedirs(train_dir, exist_ok=True)
                    safe_name = template_upload.name.replace(" ", "_").replace("-", "_")
                    img_path = os.path.join(train_dir, f"template_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}")
                    with open(img_path, "wb") as f:
                        f.write(template_upload.getvalue())
                    bundle_log += f"-> Image Reference Provided & Saved to: {img_path}\n"
                
                with open(FEEDBACK_FILE, "a") as f:
                    f.write(bundle_log)
                    
                st.rerun()

    # --- Export Section ---
    st.markdown("---")
    st.header("💾 Export Data")
    
    @st.cache_data(show_spinner="Compressing...")
    def convert_df_to_zip(df_to_convert):
        import io, zipfile
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            csv_str = df_to_convert.to_csv(index=False)
            zf.writestr('battery_batch_export.csv', csv_str)
        return buffer.getvalue()
        
    zip_data = convert_df_to_zip(master_df)
    st.download_button(
        label="Download Full Batch (ZIP Compressed)",
        data=zip_data,
        file_name="battery_batch_export.zip",
        mime='application/zip',
        key="download_zip_button"
    )
else:
    st.info("👋 Welcome! Please upload .nda files in the sidebar to begin analysis.")

# --- Feedback & Self-Improvement ---
st.markdown("---")
st.subheader("💡 Feedback & Feature Requests")
user_feedback = st.text_area("Found a bug or want a new feature? Tell the Agent.")
if st.button("Submit Feedback"):
    if user_feedback:
        log_entry = f"[{datetime.now()}] USER FEEDBACK: {user_feedback}\n"
        # 1. Local logging (if running on personal PC)
        if not st.secrets.get("is_cloud"):
            with open(FEEDBACK_FILE, "a") as f:
                f.write(log_entry)
        
        # 2. Cloud Development (GitHub Issue)
        success = create_gh_issue(f"Team Feedback: {datetime.now().strftime('%Y-%m-%d %H:%M')}", user_feedback)
        
        if success:
            st.success("Feedback pushed to GitHub! The Self-Development Agent will review this shortly.")
        else:
            st.success("Feedback logged locally!")
            if not GITHUB_TOKEN:
                st.info("💡 Tip: Add 'GITHUB_TOKEN' to Streamlit Secrets to enable automatic Agent-Fixing.")
    else:
        st.warning("Please enter some feedback before submitting.")
