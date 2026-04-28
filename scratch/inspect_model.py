import joblib
import numpy as np

file_path = r"C:\Users\user\Music\Phenix\data\checkpoints\baseline_logreg_v1.pkl"

try:
    data = joblib.load(file_path)
    print(f"Data Keys: {list(data.keys())}")
    
    if 'feature_columns' in data:
        print(f"Feature Columns (Count: {len(data['feature_columns'])}): {data['feature_columns'][:10]}...")
        
    if 'threshold' in data:
        print(f"Decision Threshold: {data['threshold']}")
        
    if 'model' in data:
        m = data['model']
        print(f"Model Type: {type(m)}")
        if hasattr(m, 'coef_'):
            print(f"Model Coefficients Shape: {m.coef_.shape}")
            
    if 'training' in data:
        print(f"Training Metadata: {data['training'].keys()}")
        if 'timestamp' in data['training']:
            print(f"Training Timestamp: {data['training']['timestamp']}")

except Exception as e:
    print(f"Error: {e}")
