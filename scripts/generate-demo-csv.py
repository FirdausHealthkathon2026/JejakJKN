"""Build the verifier demo CSVs and code-name lookup from the 1,000-claim benchmark fixture."""

import ast
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "verifier-web"
COLUMNS = [
    "nomor_klaim", "revisi_klaim", "nomor_peserta", "nama_pasien", "kode_faskes",
    "tanggal_mulai", "tanggal_selesai", "jenis_layanan", "sistem_kode", "kode",
    "jumlah", "satuan", "nominal_klaim",
]
JENIS = {
    "DIAGNOSIS": "Diagnosis",
    "PROCEDURE": "Tindakan",
    "MEDICATION": "Obat",
    "MEDICATION_DISPENSE": "Obat",
}


def seeded_catalog() -> dict[str, str]:
    source = (ROOT / "services/narrative-worker/app/domain/seed_catalog.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    return next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
    )


def main() -> None:
    claims = json.loads((ROOT / "contracts/fixtures/claims_1000_sample.json").read_text(encoding="utf-8"))
    rows = []
    for claim in claims:
        body = claim["request_payload"]
        for position, item in enumerate(body["items"]):
            rows.append({
                "nomor_klaim": claim["claim_id"],
                "revisi_klaim": body["claim_revision"],
                "nomor_peserta": body["patient"].get("participant_number", ""),
                "nama_pasien": body["patient"].get("full_name", ""),
                "kode_faskes": body["facility"]["code"],
                "tanggal_mulai": body["service_period"]["start"][:10],
                "tanggal_selesai": body["service_period"]["end"][:10],
                "jenis_layanan": JENIS[item["item_type"]],
                "sistem_kode": item["code_system"],
                "kode": item["code"],
                "jumlah": item.get("quantity", 1),
                "satuan": "" if item.get("unit", "1") == "1" else item["unit"],
                "nominal_klaim": int(claim["claim_amount_rp"]) if position == 0 else "",
            })
    public = WEB / "public"
    public.mkdir(exist_ok=True)
    with (public / "klaim_contoh_1000.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    problem = [
        dict(rows[0]),
        {**rows[1], "nomor_klaim": "311201124V000318", "tanggal_mulai": "2024-11-05", "tanggal_selesai": "2024-11-02"},
        {**rows[2], "nomor_klaim": "311201124V000331", "jumlah": 0},
    ]
    with (public / "klaim_november.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(problem)

    names = WEB / "src" / "domain" / "code_names.json"
    names.write_text(json.dumps(seeded_catalog(), ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} rows from {len(claims)} claims")


if __name__ == "__main__":
    main()
