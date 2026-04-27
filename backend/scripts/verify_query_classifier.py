import sys
import os
import json

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.query_classifier import classify_query

def test_classification(question):
    print(f"\nQuestion: {question}")
    result = classify_query(question)
    output = {
        "intent": result.intent,
        "subject": result.subject,
        "anchor_a": result.anchor_a,
        "anchor_b": result.anchor_b
    }
    print(json.dumps(output, indent=2))

def run_tests():
    test_cases = [
        "What medications is Sarah taking?",
        "When did chest pain first appear?",
        "Compare her first and most recent visit",
        "How is April 2025 different from June 2025?",
        "What's different about her last visit?",
        "Has her chest pain gotten worse?",
        "Show the progression of her fatigue",
        "Should she stop her metoprolol?",
        "How have her symptoms progressed over time?"
    ]
    
    for question in test_cases:
        test_classification(question)

if __name__ == "__main__":
    run_tests()
