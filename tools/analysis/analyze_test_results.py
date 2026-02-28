
import xml.etree.ElementTree as ET
import json
import re
import os
from collections import defaultdict

REPORT_XML = "reports/pytest_full.xml"
OUTPUT_JSON = "reports/test_fail_map.json"

def classify_failure(message, nodeid):
    """Heuristic classification of failures."""
    msg_lower = message.lower()
    
    # Time discipline mismatch (monotonic vs time.time)
    if "assert" in msg_lower and "==" in msg_lower and re.search(r'\d{6,}\.?\d*', msg_lower) and "1000.0" in msg_lower:
        return "LEGACY", "TIME_MOCK", "high"
    if "time" in msg_lower and "mock" in msg_lower:
        return "LEGACY", "TIME_MOCK", "medium"
    
    # ENV/Dependency issues
    if "modulenotfounderror" in msg_lower or "importerror" in msg_lower:
        return "ENV/FLAKY", "DEPENDENCY", "high"
    
    # Contract/Config strictness
    if "validationerror" in msg_lower or "extra inputs are not permitted" in msg_lower:
        return "CONTRACT", "STRICT_CONFIG", "high"
    if "contract" in msg_lower:
        return "CONTRACT", "CONTRACT_VIOLATION", "medium"
        
    # Risk/Exposure
    if "exposure" in nodeid.lower() or "risk" in nodeid.lower():
        if "assert" in msg_lower:
            return "CONTRACT", "RISK_MATRIX", "medium"
            
    # Legacy Tick/Signal logic
    if "assert 0 == 1" in msg_lower: # Call count mismatch often means legacy flow
        return "LEGACY", "FLOW_INTERRUPTED", "medium"
        
    return "UNKNOWN", "OTHER", "low"

def main():
    if not os.path.exists(REPORT_XML):
        print(f"File {REPORT_XML} not found.")
        return

    tree = ET.parse(REPORT_XML)
    root = tree.getroot()
    
    failures = []
    
    for testcase in root.findall(".//testcase"):
        # Check for failure or error
        failure = testcase.find("failure")
        error = testcase.find("error")
        
        nodeid = f"{testcase.get('classname')}::{testcase.get('name')}"
        file_path = testcase.get('file')
        
        elem = failure if failure is not None else error
        status = "FAIL" if failure is not None else ("ERROR" if error is not None else "PASS")
        
        if status != "PASS":
            message = elem.get("message", "")
            # Get first 3 lines of message/text (the failure details often reside in text)
            full_text = elem.text or ""
            # Combine message and first few lines of trace
            detail = f"{message}\n{full_text[:300]}".strip()
            
            classification, reason, conf = classify_failure(message + full_text, nodeid)
            
            failures.append({
                "nodeid": nodeid,
                "file": file_path,
                "status": status,
                "message_head": message[:200],
                "classification": classification,
                "reason": reason,
                "confidence": conf
            })
            
    # Group by file
    by_file = defaultdict(list)
    for f in failures:
        by_file[f['file']].append(f)
        
    # Output to JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(failures, f, indent=2)
        
    print(f"Analyzed {len(failures)} failures. Report saved to {OUTPUT_JSON}")
    
    # Print top clusters
    print("\nTop Failure Clusters:")
    sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)
    for fpath, fails in sorted_files[:10]:
        print(f"{len(fails)} : {fpath}")

if __name__ == "__main__":
    main()
