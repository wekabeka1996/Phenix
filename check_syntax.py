import subprocess

try:
    print("Testing types.py...")
    subprocess.run(['python', '-m', 'py_compile', 'apps/reference/domains/feature_engineering/types.py'], check=True)
    print("types.py OK")
    
    print("Testing calculation_engine.py...")
    subprocess.run(['python', '-m', 'py_compile', 'apps/reference/domains/feature_engineering/calculation_engine.py'], check=True)
    print("calculation_engine.py OK")
    
    print("Testing feature_engineering.py...")
    subprocess.run(['python', '-m', 'py_compile', 'apps/reference/domains/feature_engineering/feature_engineering.py'], check=True)
    print("feature_engineering.py OK")
    
except subprocess.CalledProcessError as e:
    print(f"Compilation failed: {e}")
except Exception as e:
    print(f"Error: {e}")
