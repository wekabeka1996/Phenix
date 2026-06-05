import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

class VAE_Encoder_Sim:
    """
    Симуляція навченого VAE Енкодера (через PCA).
    В реальності VAE або Contrastive Autoencoder вчиться знаходити 
    спільні приховані фактори серед великого шуму.
    """
    def __init__(self, latent_dim=4):
        self.latent_dim = latent_dim
        self.pca = PCA(n_components=latent_dim)
        
    def fit(self, X):
        self.pca.fit(X)
        
    def encode(self, X):
        return self.pca.transform(X)

if __name__ == "__main__":
    print("--- POMDP & Latent Space Generalization Simulation ---\n")
    np.random.seed(42)
    
    n_samples = 1000
    n_features = 200 # Curse of Dimensionality (кількість фічів = розміру тренувальної вибірки)
    
    # 1. Приховані режими (500 TREND, 500 FLAT)
    y_true = np.array([1]*500 + [0]*500) 
    latent_factor = np.array([1.0]*500 + [-1.0]*500)
    
    # 2. Ринкова генерація (Latent Factor Model)
    # Режим впливає на всі індикатори одночасно, але з різною силою і знаком (feature_weights)
    feature_weights = np.random.normal(loc=0.0, scale=1.0, size=(n_features,))
    X_base = np.outer(latent_factor, feature_weights)
    
    # 3. МАСИВНИЙ незалежний ринковий шум (POMDP)
    # Шум настільки великий, що повністю ховає сигнал в кожній окремій фічі
    noise = np.random.normal(loc=0.0, scale=12.0, size=(n_samples, n_features))
    X_noisy = X_base + noise
    
    # 4. Пропуски даних (NaN - імітація відриву ліквідності або збоїв датчиків)
    mask = np.random.rand(n_samples, n_features) < 0.2 # 20% NaN
    X_noisy[mask] = np.nan
    
    # Imputation: для нейромереж NaN зазвичай заповнюють 0.0 або середнім
    X_imputed = np.nan_to_num(X_noisy, nan=0.0)
    
    # 5. Train / Test Split (Оцінка здатності до узагальнення)
    # Агент бачить лише 200 станів (Train), але має працювати на наступних 800 (Test)
    X_train, X_test, y_train, y_test = train_test_split(X_imputed, y_true, test_size=0.8, random_state=42)
    
    print(f"Generated Data: {n_samples} states. Split: {len(X_train)} Train, {len(X_test)} Test.")
    print(f"Features: {n_features} with massive independent noise and 20% missing data (NaN).\n")
    
    # --- Test 1: RAW FEATURES (Curse of Dimensionality) ---
    # Оскільки n_train (200) == n_features (200), лінійна модель ідеально запам'ятає шум
    clf_raw = LogisticRegression(max_iter=1000, C=1.0) 
    clf_raw.fit(X_train, y_train)
    
    raw_train_acc = accuracy_score(y_train, clf_raw.predict(X_train))
    raw_test_acc = accuracy_score(y_test, clf_raw.predict(X_test))
    
    # --- Test 2: LATENT SPACE Z_t ---
    # Unsupervised модель (VAE/PCA) вчиться на всіх даних без міток "TREND/FLAT", 
    # щоб просто зрозуміти, як стиснути цей всесвіт до 4 чисел.
    encoder = VAE_Encoder_Sim(latent_dim=4)
    encoder.fit(X_imputed) 
    
    Z_train = encoder.encode(X_train)
    Z_test = encoder.encode(X_test)
    
    clf_latent = LogisticRegression(max_iter=1000, C=1.0)
    clf_latent.fit(Z_train, y_train)
    
    latent_train_acc = accuracy_score(y_train, clf_latent.predict(Z_train))
    latent_test_acc = accuracy_score(y_test, clf_latent.predict(Z_test))
    
    print("--- RAW FEATURES (200 dims) ---")
    print(f"In-Sample (Train) Accuracy:  {raw_train_acc:.2%} (Classic Overfitting to Noise)")
    print(f"Out-of-Sample (Test) Acc:    {raw_test_acc:.2%} (Fails on unseen market)")
    
    print("\n--- LATENT SPACE Z_t (4 dims) ---")
    print(f"In-Sample (Train) Accuracy:  {latent_train_acc:.2%}")
    print(f"Out-of-Sample (Test) Acc:    {latent_test_acc:.2%}")
    
    print("\n--- Analysis ---")
    if latent_test_acc > raw_test_acc + 0.15: # Перевага мінімум у 15%
        print("✅ SUCCESS: Latent Space successfully extracted the hidden causal structure!")
        print("While Raw Features mathematically overfit the noise (Curse of Dimensionality),")
        print("Z_t filtered the noise and allowed the agent to perfectly generalize the true market regime.")
    else:
        print("❌ FAILURE: Latent Space did not overcome the noise.")
