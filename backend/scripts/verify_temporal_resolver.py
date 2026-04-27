import sys
import os
from uuid import UUID

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.core.temporal_resolver import resolve_anchor

def test_resolution(db, patient_id, phrase, expected_num):
    result = resolve_anchor(db, patient_id, phrase)
    status = "PASS" if (result and result.visit_number == expected_num) or (result is None and expected_num is None) else "FAIL"
    
    print(f"Phrase: '{phrase:25}' | Expected: {str(expected_num):4} | Got: {str(result.visit_number if result else None):4} | Method: {str(result.resolution_method if result else 'unresolved'):20} | Status: {status}")

def run_tests():
    db = SessionLocal()
    patient_id = UUID("0a4ed618-2a37-4136-a2ba-c6411e4a3b81")
    
    print(f"{'PHRASE':27} | {'EXP':4} | {'GOT':4} | {'METHOD':20} | {'STATUS'}")
    print("-" * 80)
    
    test_cases = [
        ("first visit", 1),
        ("her last visit", 8),
        ("the most recent visit", 8),
        ("previous visit", 7),
        ("visit 3", 3),
        ("the third visit", 3),
        ("April 2025", 4),
        ("2025-04-05", 4),
        ("her June visit", None),  # unresolved (no year)
        ("before she started lisinopril", None), # unresolved (event-anchored)
        ("initial encounter", 1),
        ("current visit", 8),
        ("visit #5", 5),
        ("2nd visit", 2),
    ]
    
    for phrase, expected in test_cases:
        test_resolution(db, patient_id, phrase, expected)
    
    db.close()

if __name__ == "__main__":
    run_tests()
