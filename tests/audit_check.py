from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from backtest_engine.wrappers import BacktestExecPosFSM
from backtest_engine.mock_broker import MockBroker
from apps.reference.config_loader import ConfigLoader


def main() -> None:
    config_root = repo_root / "config" / "aurora"
    config = ConfigLoader(config_root).load_config()
    exec_pos = BacktestExecPosFSM(config=config, fsm=None, shadow_mode=False)

    assert isinstance(exec_pos.adapter, MockBroker), (
        f"Expected MockBroker, got {type(exec_pos.adapter)}"
    )

    print(f"OK: adapter is {type(exec_pos.adapter)}")


if __name__ == "__main__":
    main()
