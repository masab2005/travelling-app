import csv
import re

with open('all_segments.csv', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    segments = list(reader)

print(f"Total Segments: {len(segments)}")

# 1. Label column check (must be empty for manual annotation)
non_empty_labels = [s for s in segments if s['label'] != '']
print(f"Non-empty labels: {len(non_empty_labels)}")

# 2. Date checks
unknown_issue = [s for s in segments if s['advisory_issue_date'] == 'UNKNOWN' or not s['advisory_issue_date']]
unknown_hazard = [s for s in segments if s['hazard_date_range'] == 'UNKNOWN' or not s['hazard_date_range']]
print(f"Unknown issue dates: {len(unknown_issue)}")
print(f"Unknown hazard date ranges: {len(unknown_hazard)}")

# 3. Segment ID uniqueness check
seg_ids = [s['segment_id'] for s in segments]
unique_ids = set(seg_ids)
print(f"Unique segment IDs: {len(unique_ids)} / {len(segments)}")

# 4. Location match type check
match_type_counts = {}
for s in segments:
    mt = s['location_match_type']
    match_type_counts[mt] = match_type_counts.get(mt, 0) + 1
print("\nLocation Match Type distribution:")
for k, v in match_type_counts.items():
    print(f"  {k:26}: {v}")

# 5. Source method check
source_counts = {}
for s in segments:
    sm = s['source_method']
    source_counts[sm] = source_counts.get(sm, 0) + 1
print("\nSource Method distribution:")
for k, v in source_counts.items():
    print(f"  {k:26}: {v}")

# 6. Dir false positives check
dir_false_positives = []
for s in segments:
    if 'Dir' in s['direct_locations'].split(', '):
        real_dir = bool(re.search(r'\bDir\b', s['segment_text']))
        if not real_dir:
            dir_false_positives.append((s['pdf_filename'], s['segment_text']))

print(f"\nDir false positives: {len(dir_false_positives)}")
