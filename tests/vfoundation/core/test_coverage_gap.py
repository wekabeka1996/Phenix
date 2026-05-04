
import pytest
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.fsm_v2 import FSMv2
from vfoundation.core.protocol import Message, truncate_why
import vfoundation.obs.topology_auditor
from vfoundation.obs.topology_auditor import TopologyAuditor, HealthCheck
from vfoundation.obs.domain_bridge import DomainBridge
from pathlib import Path
import yaml
import tempfile
import time

def test_fsm_core_comprehensive():
    core = FSMCore()
    def cb(msg): pass
    
    # Listen and remove
    core.listen("EVT:E1", cb)
    core.remove_listener("EVT:E1", cb)
    assert "EVT:E1" not in core.listeners
    
    # Remove non-existent
    core.remove_listener("NON_EXISTENT", cb)
    core.listen("EVT:E2", cb)
    def another_cb(msg): pass
    core.remove_listener("EVT:E2", another_cb) # Triggers ValueError inside remove (Line 98-99)
    
    # Emit with exception
    def buggy_cb(msg): raise ValueError("bug")
    core.listen("EVT:E3", buggy_cb)
    core.emit("EVT:E3", {}, "test") # Should log and continue (Line 75-82)
    
    # Emit with rid
    received = []
    def rid_cb(msg): received.append(msg)
    core.listen("EVT:RID", rid_cb)
    core.emit("EVT:RID", {}, "test", rid="r1")
    assert received[0].rid == "r1"
    
    # Domains
    core.register_domain("d1", "inst")
    assert core.get_domain("d1") == "inst" # Line 122
    assert core.get_domain("d2") is None

def test_fsm_v2_comprehensive():
    fsm = FSMv2("test")
    fsm.register_state("S1", initial=True)
    fsm.register_state("S2")
    
    # set_state valid
    fsm.set_state("k1", "S1") # Line 174-175
    # set_state unknown (Line 173)
    with pytest.raises(ValueError, match="Unknown state"):
        fsm.set_state("k1", "UNKNOWN")
    
    # Callback exceptions (Line 256-257, 267-268)
    def exit_bug(k, s, m): raise RuntimeError("exit fail")
    def enter_bug(k, s, m): raise RuntimeError("enter fail")
    
    fsm3 = FSMv2("callbacks")
    fsm3.register_state("A", initial=True, on_exit=exit_bug)
    fsm3.register_state("B", on_enter=enter_bug)
    fsm3.register_transition("A", "EVT:GO", "B")
    
    msg = Message(op="EVT", verb="GO", src="s", dst="d", pld={}, why="w")
    fsm3.handle("key1", msg) # Should not crash
    
    # validate_reachability with duplicate in queue (Line 336)
    fsm2 = FSMv2("hit336")
    fsm2.register_state("A", initial=True)
    fsm2.register_state("B")
    fsm2.register_transition("A", "EVT:1", "B")
    fsm2.register_transition("A", "EVT:2", "B")
    fsm2.validate_reachability()

def test_domain_bridge_comprehensive():
    class BuggyBus:
        def emit(self, *args, **kwargs):
            raise RuntimeError("emit fail")
    
    bus = BuggyBus()
    bridge = DomainBridge("buggy", bus=bus)
    bridge.register_health_fn(lambda: True)
    
    # Trigger line 60-61 (emit failed)
    bridge.emit_status()

def test_topology_auditor_extra_coverage():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Test _detect_repo_root fallback (Line 213)
        TopologyAuditor._detect_repo_root()
        
        # Test audit with drift (Line 124-135, 137)
        bus = FSMCore()
        bus.register_domain("extra_domain", "inst")
        
        registry_file = tmp_path / "registry.yaml"
        with open(registry_file, "w") as f:
            yaml.dump({"registry": [{"verb": "V", "owner": "expected"}]}, f)
            
        auditor = TopologyAuditor(bus=bus, repo_root=tmp_path, registry_path="registry.yaml")
        
        # Audit with drift
        report = auditor.audit()
        assert "expected" in report.missing
        
        # Audit OK (Line 137)
        bus.register_domain("expected", "inst")
        report_ok = auditor.audit()
        assert report_ok.healthy is True
        
        # Test get_expected_owners (Line 181)
        assert auditor.get_expected_owners() == {"expected"}
        
        # Test no YAML warning (Line 187-188)
        original_has_yaml = vfoundation.obs.topology_auditor.HAS_YAML
        vfoundation.obs.topology_auditor.HAS_YAML = False
        try:
            auditor_no_yaml = TopologyAuditor(repo_root=tmp_path, registry_path="registry.yaml")
            assert auditor_no_yaml.get_expected_owners() == set()
        finally:
            vfoundation.obs.topology_auditor.HAS_YAML = original_has_yaml

def test_protocol_coverage_gaps():
    # truncate_why (Line 16-20)
    assert truncate_why(None) is None
    assert truncate_why("short") == "short"
    assert truncate_why("a" * 100) == "a" * 80
    
    # ttl_ms out of range (Line 55-57)
    with pytest.raises(ValueError, match="ttl_ms out of allowed range"):
        Message(op="EVT", verb="V", src="s", dst="d", ttl_ms=0)
    
    with pytest.raises(ValueError, match="ttl_ms out of allowed range"):
        Message(op="EVT", verb="V", src="s", dst="d", ttl_ms=30001)
        
    # why length (Line 63)
    with pytest.raises(ValueError, match="why must be <=80 chars"):
        Message(op="EVT", verb="V", src="s", dst="d", why="a" * 81)
        
    # is_expired (Line 67)
    msg = Message(op="EVT", verb="V", src="s", dst="d", ttl_ms=10)
    time.sleep(0.02)
    assert msg.is_expired() is True
    
    # typed_payload (Line 82)
    from pydantic import BaseModel
    class MySchema(BaseModel):
        f: int
    msg = Message(op="EVT", verb="V", src="s", dst="d", pld={"f": 1})
    obj = msg.typed_payload(MySchema)
    assert obj.f == 1
