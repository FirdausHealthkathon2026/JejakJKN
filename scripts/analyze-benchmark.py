import json

with open('contracts/fixtures/benchmark_results_1000.json') as f:
    data = json.load(f)

fp = [r for r in data['results'] if r['scenario'] == 'VALID' and r['detected_as_fraud']]
print(f"Total VALID flagged (False Positives): {len(fp)}")
findings_count = {}
for r in fp:
    for f in r.get('findings', []):
        findings_count[f] = findings_count.get(f, 0) + 1
    if not r.get('findings'):
        status = f"enc:{r.get('encounter_match')}, recon:{r.get('evidence_recon')}, status:{r.get('status')}"
        findings_count[status] = findings_count.get(status, 0) + 1

print("Reasons for False Positives:", findings_count)
for r in fp[:3]:
    print(r)
