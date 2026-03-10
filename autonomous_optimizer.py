import os
import time
import requests
import json
import subprocess
from datetime import datetime

# --- Configuration ---
GITHUB_REPO = "wt-phatchara/cest-battery-dashboard"
# Recommendation: Set this in your Windows Environment Variables for security
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "") 
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "deepseek-coder" # Best for coding tasks

# Files the agent is allowed to touch
CORE_FILES = ["streamlit_app.py", "logic_parsing.py", "logic_electrochem.py"]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🤖 {msg}")

def get_new_issues():
    """Fetches open issues from GitHub."""
    if not GITHUB_TOKEN:
        log("Error: No GITHUB_TOKEN found. Cannot check for feedback.")
        return []
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues?state=open"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        log(f"GitHub Poll Failed: {e}")
    return []

def get_codebase():
    """Reads core files into a single context string."""
    context = ""
    for filename in CORE_FILES:
        if os.path.exists(filename):
            with open(filename, "r") as f:
                context += f"\n\nFILE: {filename}\n"
                context += "```python\n" + f.read() + "\n```"
    return context

def ask_ollama(prompt):
    """Sends prompt to local Ollama instance."""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": 16384} # Large context for codebase
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=300)
        if response.status_code == 200:
            return response.json().get("response", "")
    except Exception as e:
        log(f"Ollama Connection Failed: {e}")
    return ""

def apply_fix(issue_title, issue_body):
    """Orchestrates the fix for a specific issue."""
    log(f"Processing Issue: {issue_title}")
    
    codebase = get_codebase()
    system_rules = open("agents.md", "r").read() if os.path.exists("agents.md") else ""

    prompt = f"""
    {system_rules}

    # TASK
    A user has reported an issue/request:
    TITLE: {issue_title}
    DESCRIPTION: {issue_body}

    # CURRENT CODE
    {codebase}

    # INSTRUCTION
    Return ONLY the full corrected content of the files that need changing. 
    Format your response as:
    --- START FILE: filename ---
    [CODE HERE]
    --- END FILE: filename ---
    """

    suggestion = ask_ollama(prompt)
    if not suggestion:
        return False

    # Parsing logic (primitive extract)
    changes_made = False
    for filename in CORE_FILES:
        start_marker = f"--- START FILE: {filename} ---"
        end_marker = f"--- END FILE: {filename} ---"
        if start_marker in suggestion and end_marker in suggestion:
            new_code = suggestion.split(start_marker)[1].split(end_marker)[0].strip()
            
            # Remove any triple backticks the LLM might have included
            if new_code.startswith("```python"): new_code = new_code[9:]
            if new_code.endswith("```"): new_code = new_code[:-3]
            new_code = new_code.strip()

            # --- Safety Check: Syntax Validation ---
            temp_file = f"temp_{filename}"
            with open(temp_file, "w") as tf:
                tf.write(new_code)
            
            check = subprocess.run(["python", "-m", "py_compile", temp_file], capture_output=True)
            if check.returncode == 0:
                with open(filename, "w") as f:
                    f.write(new_code)
                log(f"✅ Successfully refactored {filename}")
                changes_made = True
            else:
                log(f"❌ Syntax Error detected in suggestion for {filename}. Aborting update.")
            
            if os.path.exists(temp_file): os.remove(temp_file)

    return changes_made

def main_loop():
    log("Autonomous Optimizer Started. Polling GitHub every 5 minutes...")
    while True:
        issues = get_new_issues()
        if issues:
            log(f"Found {len(issues)} open issues.")
            for issue in issues:
                success = apply_fix(issue['title'], issue['body'])
                if success:
                    # Commit and Push
                    subprocess.run(["git", "add", "."])
                    subprocess.run(["git", "commit", "-m", f"Auto-Fix for Issue #{issue['number']}: {issue['title']}"])
                    subprocess.run(["git", "push", "origin", "master"])
                    
                    # Close issue on GitHub
                    issue_url = f"https://api.github.com/repos/{GITHUB_REPO}/issues/{issue['number']}"
                    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
                    requests.patch(issue_url, headers=headers, json={"state": "closed"})
                    log(f"🚀 Fixed and Closed Issue #{issue['number']}.")
        else:
            log("Sleep mode: No new feedback found.")
        
        time.sleep(300) # Poll every 5 minutes

if __name__ == "__main__":
    main_loop()
