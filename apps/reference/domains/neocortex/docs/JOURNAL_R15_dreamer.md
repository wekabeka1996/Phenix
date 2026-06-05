# Phase R1.5: The Dreamer - Offline Consolidation

**Date:** 2026-01-10
**Author:** Antigravity AI
**Phase:** R1.5 (Graph-based Memory Consolidation)

---

## Overview

Implemented offline "dreamer" module that consolidates raw episode experience 
into a persistent CausalGraph stored in SQLite. This enables:

1. **Long-term Memory**: Experience persists across restarts
2. **State Clustering**: Similar latent states share graph nodes
3. **Curiosity Bonus**: Visit counts enable exploration incentives
4. **Future Planning**: Graph structure enables look-ahead decisions

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         Dreamer                              │
│                                                              │
│   Input: List[Episode]                                       │
│      │                                                       │
│      ▼                                                       │
│   ┌────────────────────────────────────┐                    │
│   │ For each episode:                   │                    │
│   │   1. Encode features → z            │                    │
│   │   2. Build transitions (z,a,r,z')   │                    │
│   │   3. Add to CausalGraph             │                    │
│   └────────────────────────────────────┘                    │
│      │                                                       │
│      ▼                                                       │
│   Prune (remove weak edges)                                  │
│      │                                                       │
│      ▼                                                       │
│   Output: Updated hippocampus.db                             │
└──────────────────────────────────────────────────────────────┘
```

---

## Files Created

| File | Purpose |
|------|---------|
| `logic/memory/graph.py` | CausalGraph - SQLite-backed state transition graph |
| `logic/dreamer.py` | Dreamer - Episode consolidation module |
| `tests/test_dreamer.py` | 16 comprehensive tests |

## Files Modified

| File | Changes |
|------|---------|
| `logic/brain/worker.py` | Added `_brain_dream_task`, `_brain_get_curiosity_task` |
| `logic/brain/bridge.py` | Added `dream_async()`, `get_curiosity_async()` |
| `transport/adapter.py` | Added dream control, episode collection |
| `logic/memory/__init__.py` | Exports for graph classes |

---

## SQLite Schema

**Table: nodes**
```sql
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    z_centroid BLOB NOT NULL,     -- np.float32.tobytes()
    visit_count INTEGER DEFAULT 1,
    avg_value REAL DEFAULT 0.0,
    created_at REAL DEFAULT 0.0
);
```

**Table: edges**
```sql
CREATE TABLE edges (
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    action INTEGER NOT NULL,       -- 0=LONG, 1=SHORT, 2=FLAT
    reward_mean REAL DEFAULT 0.0,
    reward_var REAL DEFAULT 0.0,   -- Welford's online variance
    count INTEGER DEFAULT 1,
    PRIMARY KEY (source_id, target_id, action)
);
```

---

## Key Algorithms

### Node Clustering

When adding a transition `(z_t, a, r, z_next)`:
1. Find closest existing node within `cluster_radius` (Euclidean distance)
2. If found → Update centroid incrementally: `c_new = (c_old * n + z) / (n + 1)`
3. If not found → Create new node

### Edge Updates (Welford's Algorithm)

Online running mean/variance for reward statistics:
```python
delta = reward - old_mean
new_mean = old_mean + delta / new_n
delta2 = reward - new_mean
new_var = old_var + delta * delta2
```

### Curiosity Bonus

ICM-style intrinsic motivation:
```python
curiosity = 1.0 / sqrt(max(1, visit_count))
```

---

## Triggering Conditions

Dream consolidation triggers when:
1. `episodes_collected >= 100` (max_episodes_before_dream), OR
2. `training_steps >= 1000` since last dream AND episodes > 0

---

## Test Results

```
tests/test_dreamer.py: 16 passed ✅
- CausalGraph SQLite operations (9 tests)
- Dreamer consolidation logic (5 tests)
- Integration tests (2 tests)
```

---

## Usage

```python
# Adapter collects episodes
await adapter.add_completed_episode(episode)

# Auto-triggers dream when threshold reached
# Or force manually:
await adapter.force_dream()

# Database created at:
# data/hippocampus.db
```

---

## Next Steps

1. **Phase R2**: Use graph for planning (Monte Carlo Tree Search)
2. **FAISS Integration**: Replace Euclidean search for >10k nodes
3. **Curiosity Integration**: Add bonus to PPO reward signal
