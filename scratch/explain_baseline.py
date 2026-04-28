import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

file_path = r"C:\Users\user\Music\Phenix\data\checkpoints\baseline_logreg_v1.pkl"

def explain_model():
    data = joblib.load(file_path)
    pipeline = data['model']
    threshold = data['threshold']
    
    if not isinstance(pipeline, Pipeline):
        print("Error: Model is not a pipeline.")
        return
        
    preprocessor = pipeline.named_steps['preprocess']
    classifier = pipeline.named_steps['model']
    
    # Get feature names after transformation
    try:
        # We need the original feature names to pass to get_feature_names_out
        feature_names = preprocessor.get_feature_names_out()
    except Exception as e:
        print(f"Error getting feature names: {e}")
        # Fallback to generic names if get_feature_names_out fails
        feature_names = [f"feat_{i}" for i in range(len(classifier.coef_[0]))]

    weights = classifier.coef_[0]
    importance = pd.DataFrame({
        'feature': feature_names,
        'weight': weights
    })
    
    print("\n--- Top 5 Features pushing towards BLOCK (High Risk) ---")
    print(importance.sort_values(by='weight', ascending=False).head(5).to_string(index=False))
    
    print("\n--- Top 5 Features pushing towards ALLOW (Safe) ---")
    print(importance.sort_values(by='weight', ascending=True).head(5).to_string(index=False))
    
    intercept = classifier.intercept_[0]
    print(f"\nModel Intercept (Base Bias): {intercept:.4f}")
    
    logit_threshold = np.log(threshold / (1 - threshold))
    print(f"Logit Threshold (for P={threshold}): {logit_threshold:.4f}")

if __name__ == "__main__":
    explain_model()
