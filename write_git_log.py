import subprocess

def run_git_log_to_file():
    try:
        # Get log for the specific file and save it to output.txt
        result = subprocess.run(
            ['git', 'log', '-p', '--', 'config/mean_reversion.yaml'], 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        with open('git_log_output.txt', 'w', encoding='utf-8') as f:
            f.write(result.stdout)
            
        print("Git log written to git_log_output.txt")
        
    except Exception as e:
        print(f"Error: {e}")

run_git_log_to_file()
