"""
Generates historical_complaints.csv (260 archived records, 2021-2023)
and officers.csv (15 field officers) for MediGuard historical analysis.
Run from project root: python generate_data.py
"""
import csv, random, uuid, datetime, os

random.seed(42)

MEDICINE_IDS = [
    ('MED-F1BD0EC9', 8.5),   # Amoxicillin
    ('MED-80150E17', 18.0),  # Azithromycin
    ('MED-59EB08A3', 12.0),  # Ciprofloxacin
    ('MED-94DCD221', 6.0),   # Metronidazole
    ('MED-1711A01F', 2.5),   # Paracetamol
    ('MED-D0A5410E', 4.0),   # Ibuprofen
    ('MED-FB58034C', 22.0),  # Tramadol
    ('MED-B036DD9C', 95.0),  # Oseltamivir
    ('MED-0A195B42', 14.0),  # Acyclovir
    ('MED-C029044A', 9.0),   # Amlodipine
    ('MED-B85A6ED2', 5.5),   # Metformin
    ('MED-99B74A7E', 25.0),  # Atorvastatin
    ('MED-87F56986', 8.0),   # Omeprazole
    ('MED-B71DF9FF', 6.5),   # Loratadine
]
MED_PRICE = {m: p for m, p in MEDICINE_IDS}

FACILITY_IDS = [
    'FAC-EF8B79A0', 'FAC-FFDD0B04', 'FAC-2D52E3F2', 'FAC-E691F464',
    'FAC-F9EE4390', 'FAC-317EFB40', 'FAC-952F7C35', 'FAC-DCD759AF', '',
]

DESCRIPTIONS = [
    'Blister pack labelling inconsistent with MOH-registered product.',
    'Expiry date appears tampered — original date scratched off.',
    'Online purchase via Telegram; seller account now deleted.',
    'Multiple neighbours bought same batch; all reported ineffectiveness.',
    'Medicine purchased from street vendor near the market.',
    'Price was 60% below standard — suspect adulterated product.',
    'Packaging seal already broken upon purchase.',
    'Chemical smell inconsistent with known product.',
    'Holographic seal missing from packaging.',
    'Tablets crumbled unusually — suspect substandard binding agents.',
    'Colour of tablets differs noticeably from genuine product.',
    'No batch number printed on secondary packaging.',
]

# Historical clusters (already raided / archived)
CLUSTERS = [
    {
        'name': 'Op. Selatan 2021',
        'center': (1.490, 103.760), 'spread': 0.040, 'count': 55,
        'date_range': ('2021-01-10', '2021-06-28'),
        'top_med': 'MED-FB58034C',
        'other_meds': ['MED-94DCD221', 'MED-F1BD0EC9', 'MED-D0A5410E'],
        'district': 'Johor Bahru', 'city': 'Johor Bahru',
        'state': 'Johor', 'postcode': '80000',
    },
    {
        'name': 'Op. Pulau 2021',
        'center': (5.418, 100.328), 'spread': 0.030, 'count': 45,
        'date_range': ('2021-03-05', '2021-08-20'),
        'top_med': 'MED-1711A01F',
        'other_meds': ['MED-D0A5410E', 'MED-B71DF9FF', 'MED-94DCD221'],
        'district': 'Timur Laut', 'city': 'Georgetown',
        'state': 'Penang', 'postcode': '10050',
    },
    {
        'name': 'Op. Utama 2022',
        'center': (3.162, 101.698), 'spread': 0.025, 'count': 60,
        'date_range': ('2022-01-15', '2022-06-30'),
        'top_med': 'MED-B85A6ED2',
        'other_meds': ['MED-C029044A', 'MED-99B74A7E', 'MED-87F56986'],
        'district': 'Kuala Lumpur', 'city': 'Kuala Lumpur',
        'state': 'Kuala Lumpur', 'postcode': '50350',
    },
    {
        'name': 'Op. Selangor 2022',
        'center': (3.074, 101.531), 'spread': 0.035, 'count': 45,
        'date_range': ('2022-07-01', '2022-12-15'),
        'top_med': 'MED-C029044A',
        'other_meds': ['MED-B85A6ED2', 'MED-87F56986', 'MED-99B74A7E'],
        'district': 'Petaling', 'city': 'Shah Alam',
        'state': 'Selangor', 'postcode': '40150',
    },
    {
        'name': 'Op. Kinta 2023',
        'center': (4.592, 101.088), 'spread': 0.030, 'count': 35,
        'date_range': ('2023-01-08', '2023-06-25'),
        'top_med': 'MED-F1BD0EC9',
        'other_meds': ['MED-80150E17', 'MED-59EB08A3', 'MED-94DCD221'],
        'district': 'Kinta', 'city': 'Ipoh',
        'state': 'Perak', 'postcode': '30000',
    },
]

SCATTER_LOCS = [
    (2.730, 101.940, 'Seremban', 'Seremban', 'Negeri Sembilan', '70000'),
    (3.043, 101.445, 'Nilai', 'Nilai', 'Negeri Sembilan', '71800'),
    (3.122, 101.656, 'Damansara', 'Petaling Jaya', 'Selangor', '47810'),
    (2.152, 102.252, 'Melaka Tengah', 'Melaka', 'Melaka', '75000'),
    (6.120, 100.368, 'Kota Setar', 'Alor Setar', 'Kedah', '05000'),
    (3.820, 103.326, 'Kuantan', 'Kuantan', 'Pahang', '25000'),
]


def _make_row(lat, lng, med_id, date, district, city, state, postcode):
    std = MED_PRICE.get(med_id, 10.0)
    reported = round(std * random.uniform(0.28, 0.85), 2)
    loss = round(max(0.0, (std - reported) * random.uniform(0.85, 1.40)), 2)
    return {
        'complaint_id': f'HMP-{uuid.uuid4().hex[:8].upper()}',
        'date': date.isoformat(),
        'lat': round(lat, 6),
        'lng': round(lng, 6),
        'medicine_id': med_id,
        'purchased_from_facility_id': random.choice(FACILITY_IDS),
        'description': random.choice(DESCRIPTIONS),
        'reported_price': reported,
        'standard_price': std,
        'estimated_loss': loss,
        'verified': random.random() > 0.42,
        'district': district,
        'city': city,
        'state': state,
        'postcode': postcode,
    }


rows = []

for cl in CLUSTERS:
    d0 = datetime.date.fromisoformat(cl['date_range'][0])
    d1 = datetime.date.fromisoformat(cl['date_range'][1])
    span = (d1 - d0).days
    clat, clng = cl['center']
    sp = cl['spread']

    for _ in range(cl['count']):
        r = random.random()
        med = cl['top_med'] if r < 0.58 else (
            random.choice(cl['other_meds']) if r < 0.88 else
            random.choice(MEDICINE_IDS)[0]
        )
        lat = clat + random.gauss(0, sp)
        lng = clng + random.gauss(0, sp)
        d = d0 + datetime.timedelta(days=random.randint(0, span))
        rows.append(_make_row(lat, lng, med, d,
                              cl['district'], cl['city'], cl['state'], cl['postcode']))

# Scatter noise — 20 complaints
for _ in range(20):
    loc = random.choice(SCATTER_LOCS)
    d = datetime.date(2021, 1, 1) + datetime.timedelta(days=random.randint(0, 899))
    med = random.choice(MEDICINE_IDS)[0]
    lat = loc[0] + random.uniform(-0.06, 0.06)
    lng = loc[1] + random.uniform(-0.06, 0.06)
    rows.append(_make_row(lat, lng, med, d, loc[2], loc[3], loc[4], loc[5]))

FIELDS = [
    'complaint_id', 'date', 'lat', 'lng', 'medicine_id',
    'purchased_from_facility_id', 'description', 'reported_price',
    'standard_price', 'estimated_loss', 'verified',
    'district', 'city', 'state', 'postcode',
]
out_path = os.path.join(os.path.dirname(__file__), 'backend', 'data', 'historical_complaints.csv')
with open(out_path, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)
print(f"Wrote {len(rows)} rows -> {out_path}")

# ── Officers ───────────────────────────────────────────────────────────────
OFFICERS = [
    ('OFF-001', 'Insp. Ahmad Shahril',    'Field Operations', 'Kuala Lumpur',    'Inspector'),
    ('OFF-002', 'DSP Nurul Aina',          'Enforcement',      'Selangor',        'Deputy Superintendent'),
    ('OFF-003', 'Insp. Haziq Razali',      'Field Operations', 'Johor',           'Inspector'),
    ('OFF-004', 'Sgt. Farah Husin',        'Investigation',    'Penang',          'Sergeant'),
    ('OFF-005', 'Insp. Syafiq Naim',       'Field Operations', 'Perak',           'Inspector'),
    ('OFF-006', 'DSP Roslan Md Nor',       'Enforcement',      'Negeri Sembilan', 'Deputy Superintendent'),
    ('OFF-007', 'Insp. Wan Nabilah',       'Field Operations', 'Melaka',          'Inspector'),
    ('OFF-008', 'Sgt. Hafizuddin',         'Investigation',    'Kedah',           'Sergeant'),
    ('OFF-009', 'Insp. Zulaikha Rahim',    'Field Operations', 'Kuala Lumpur',    'Inspector'),
    ('OFF-010', 'DSP Azizul Hakim',        'Enforcement',      'Selangor',        'Deputy Superintendent'),
    ('OFF-011', 'Insp. Norzaida',          'Field Operations', 'Johor',           'Inspector'),
    ('OFF-012', 'Sgt. Khairul Azlan',      'Investigation',    'Penang',          'Sergeant'),
    ('OFF-013', 'Insp. Izwan Fauzi',       'Field Operations', 'Perak',           'Inspector'),
    ('OFF-014', 'DSP Sharifah Maisarah',   'Enforcement',      'Selangor',        'Deputy Superintendent'),
    ('OFF-015', 'Insp. Fadzillah Nordin',  'Field Operations', 'Johor',           'Inspector'),
]
off_path = os.path.join(os.path.dirname(__file__), 'backend', 'data', 'officers.csv')
with open(off_path, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['officer_id', 'name', 'department', 'state', 'rank'])
    w.writeheader()
    for o in OFFICERS:
        w.writerow(dict(zip(['officer_id', 'name', 'department', 'state', 'rank'], o)))
print(f"Wrote {len(OFFICERS)} officers -> {off_path}")
