import subprocess
import re

def run_git_command():
    try:
        # Get log for the specific file
        result = subprocess.run(
            ['git', 'log', '-p', '--', 'config/mean_reversion.yaml'], 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        output = result.stdout
        
        # Parse commits to find when the change happened
        commits = output.split('
commit ')
        
        for commit in commits:
            if not commit.startswith('commit '):
                commit = 'commit ' + commit
                
            # Check if this commit has the specific change
            if '-  timeframe_sec: 180' in commit and '+  timeframe_sec: 300' in commit:
                lines = commit.split('
')
                print("FOUND THE EXACT CHANGE:")
                for i in range(5):
                    if i < len(lines):
                        print(lines[i])
                return
                
            # Or if it's the other way around
            if '-  timeframe_sec: 300' in commit and '+  timeframe_sec: 180' in commit:
                lines = commit.split('
')
                print("FOUND THE REVERSE CHANGE (300 -> 180):")
                for i in range(5):
                    if i < len(lines):
                        print(lines[i])
                return

        print("Did not find the exact change in config/mean_reversion.yaml")
        
        # Try to search globally if not found in that specific file
        print("
Searching globally across all files for this change...")
        result_global = subprocess.run(
            ['git', 'log', '-S', 'timeframe_sec: 300', '--oneline'], 
            capture_output=True, 
            text=True
        )
        print(result_global.stdout[:500])
        
    except Exception as e:
        print(f"Error: {e}")

run_git_command()
