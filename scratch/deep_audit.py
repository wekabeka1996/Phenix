import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

file_path = r"C:\Users\user\Music\Phenix\data\checkpoints\baseline_logreg_v1.pkl"

def deep_audit():
    data = joblib.load(file_path)
    pipeline = data['model']
    feature_columns = data['feature_columns']
    
    preprocessor = pipeline.named_steps['preprocess']
    classifier = pipeline.named_steps['model']
    
    feature_names = preprocessor.get_feature_names_out()
    weights = classifier.coef_[0]
    
    importance = pd.DataFrame({
        'feature': feature_names,
        'weight': weights
    }).sort_values(by='weight', ascending=False)
    
    # Save full weights to a CSV for record
    importance.to_csv("scratch/full_model_weights.csv", index=False)
    
    print("--- Full Weights Summary ---")
    print(f"Total features: {len(importance)}")
    print(f"Positive weights (BLOCK): {len(importance[importance.weight > 0])}")
    print(f"Negative weights (ALLOW): {len(importance[importance.weight < 0])}")
    
    print("\n--- Training Metadata Audit ---")
    training = data.get('training', {})
    for k, v in training.items():
        print(f"  {k}: {v}")
        
    print("\n--- Distribution of Weights ---")
    print(importance['weight'].describe())
    
    # Check for suspicious features (leakage candidates)
    leakage_keywords = ['pnl', 'target', 'label', 'profit', 'loss', 'return']
    suspicious = importance[importance['feature'].str.contains('|'.join(leakage_keywords), case=False)]
    if not suspicious.empty:
        print("\n--- Suspicious Features (Potential Leakage) ---")
        print(suspicious.to_string(index=False))
    else:
        print("\nNo obvious leakage features found by keyword search.")

if __name__ == "__main__":
    deep_audit()
