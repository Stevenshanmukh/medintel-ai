from app.core.entities import extract_entities

# The September 2024 case: doctor asks, patient denies
sept_2024 = '''Doctor: That is still good. Any chest pain, palpitations, shortness of breath?

Patient: Um, no, not really. I get winded if I rush up the stairs but I think that is just being out of shape.'''

print('=== September 2024 case ===')
for e in extract_entities(sept_2024):
    src = e.extra.get('negation_source', 'negspacy/default')
    print(f'  {e.entity_type:12} | {e.entity_text:25} | negated={e.negated} | source={src}')

# The January 2025 case: doctor asks about chest heaviness, patient denies *radiation*
jan_2025 = '''Doctor: when this happens, the chest heaviness, do you ever notice your jaw, your shoulder, anything in your back?

Patient: No, just the chest itself.'''

print()
print('=== January 2025 case ===')
for e in extract_entities(jan_2025):
    src = e.extra.get('negation_source', 'negspacy/default')
    print(f'  {e.entity_type:12} | {e.entity_text:25} | negated={e.negated} | source={src}')
