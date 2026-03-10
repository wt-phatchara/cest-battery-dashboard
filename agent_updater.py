import os
from datetime import datetime

FEEDBACK_FILE = "feedback_log.txt"
PROJECT_FILES = ["app.py", "logic_electrochem.py", "logic_parsing.py"]

def read_feedback():
    """Reads the local feedback log."""
    if not os.path.exists(FEEDBACK_FILE):
        return "No feedback logged yet."
    with open(FEEDBACK_FILE, "r") as f:
        return f.read()

def read_codebase() -> str:
    """Reads the current project codebase for context."""
    code_context = []
    for file in PROJECT_FILES:
        if os.path.exists(file):
            with open(file, "r") as f:
                code_context.append(f"\n--- {file} ---\n")
                code_context.append(f.read())
    return "".join(code_context)

def generate_update_prompt():
    """
    Constructs a prompt that can be sent to an LLM 
    to generate the next version of the application.
    """
    feedback = read_feedback()
    code = read_codebase()
    
    prompt = f"""
# SYSTEM INSTRUCTION
You are an expert material science developer. Your task is to update the 'Battery Performance Auto-Plotter' 
web application based on the user feedback below.

# CURRENT CODEBASE
{code}

# USER FEEDBACK & ERROR LOGS
{feedback}

# TASK
1. Analyze the feedback for bugs or requested features.
2. Generate 'app_v_next.py' which incorporates these changes.
3. Keep the styling premium and ensure all calculations remain vectorized.
"""
    return prompt

if __name__ == "__main__":
    print(f"--- Agent Updater Initialized [{datetime.now()}] ---")
    prompt = generate_update_prompt()
    # In a full automation flow, this prompt would be sent to an LLM API.
    # For now, we output it to a file for human review/processing.
    with open("update_prompt_v_next.txt", "w") as f:
        f.write(prompt)
    print("Update prompt generated in 'update_prompt_v_next.txt'.")
