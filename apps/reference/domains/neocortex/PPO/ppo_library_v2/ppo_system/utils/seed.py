# path: ppo_library/ppo_system/utils/seed.py
import os
import random
import numpy as np
import torch

def set_global_seed(seed: int):
    """Встановлює seed для всіх основних бібліотек для відтворюваності."""
    os.environ['PYTHONHASHSEED'] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False