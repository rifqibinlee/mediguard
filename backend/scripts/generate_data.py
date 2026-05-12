"""
generate_data.py
Generates synthetic Malaysian healthcare fraud test data.
Run from the project root:  python backend/scripts/generate_data.py
Outputs CSVs to:           backend/data/
"""

import os, uuid, random, math
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# 1.  GEO REFERENCE DATA
# ─────────────────────────────────────────────────────────────────────────────

STATES = {
    "Kuala Lumpur": {
        "center": (3.1390, 101.6869),
        "districts": [
            ("Chow Kit",     "Kuala Lumpur", "50350"),
            ("Brickfields",  "Kuala Lumpur", "50470"),
            ("Bangsar",      "Kuala Lumpur", "59000"),
            ("Kepong",       "Kuala Lumpur", "52100"),
            ("Wangsa Maju",  "Kuala Lumpur", "53300"),
            ("Titiwangsa",   "Kuala Lumpur", "53200"),
            ("Sentul",       "Kuala Lumpur", "51000"),
            ("Seputeh",      "Kuala Lumpur", "58000"),
        ],
    },
    "Selangor": {
        "center": (3.0738, 101.5183),
        "districts": [
            ("Petaling Jaya", "Petaling Jaya", "47800"),
            ("Shah Alam",     "Shah Alam",     "40000"),
            ("Subang Jaya",   "Subang Jaya",   "47500"),
            ("Klang",         "Klang",          "41000"),
            ("Ampang",        "Ampang",         "68000"),
            ("Kajang",        "Kajang",         "43000"),
            ("Puchong",       "Puchong",        "47100"),
            ("Sepang",        "Sepang",         "43900"),
        ],
    },
    "Johor": {
        "center": (1.4927, 103.7414),
        "districts": [
            ("Johor Bahru",      "Johor Bahru",      "80000"),
            ("Skudai",           "Johor Bahru",      "81300"),
            ("Iskandar Puteri",  "Johor Bahru",      "79100"),
            ("Batu Pahat",       "Batu Pahat",       "83000"),
            ("Muar",             "Muar",             "84000"),
            ("Kulai",            "Kulai",            "81000"),
        ],
    },
    "Penang": {
        "center": (5.4141, 100.3288),
        "districts": [
            ("Georgetown",       "Georgetown",       "10000"),
            ("Bayan Lepas",      "Bayan Lepas",      "11900"),
            ("Butterworth",      "Butterworth",      "12000"),
            ("Bukit Mertajam",   "Bukit Mertajam",   "14000"),
            ("Seberang Perai",   "Perai",            "13600"),
        ],
    },
    "Perak": {
        "center": (4.5975, 101.0901),
        "districts": [
            ("Ipoh",        "Ipoh",        "30000"),
            ("Taiping",     "Taiping",     "34000"),
            ("Teluk Intan", "Teluk Intan", "36000"),
            ("Manjung",     "Seri Manjung","32000"),
            ("Kampar",      "Kampar",      "31400"),
        ],
    },
    "Kedah": {
        "center": (6.1184, 100.3685),
        "districts": [
            ("Alor Setar",    "Alor Setar",    "05000"),
            ("Sungai Petani", "Sungai Petani", "08000"),
            ("Kulim",         "Kulim",         "09000"),
            ("Langkawi",      "Kuah",          "07000"),
        ],
    },
    "Negeri Sembilan": {
        "center": (2.7297, 101.9381),
        "districts": [
            ("Seremban",     "Seremban",     "70000"),
            ("Port Dickson", "Port Dickson", "71000"),
            ("Nilai",        "Nilai",        "71800"),
            ("Rembau",       "Rembau",       "71300"),
        ],
    },
    "Melaka": {
        "center": (2.1896, 102.2501),
        "districts": [
            ("Melaka Tengah", "Melaka",      "75000"),
            ("Alor Gajah",    "Alor Gajah",  "78000"),
            ("Jasin",         "Jasin",       "77000"),
        ],
    },
}

FRAUD_HOTSPOTS = [
    {"label": "Chow Kit Night Market Zone",  "center": (3.1620, 101.6980), "radius_km": 0.6,  "weight": 0.20},
    {"label": "Klang Pasar Borong",           "center": (3.0450, 101.4450), "radius_km": 0.5,  "weight": 0.15},
    {"label": "Johor Bahru Informal Market",  "center": (1.4600, 103.7600), "radius_km": 0.4,  "weight": 0.12},
    {"label": "Georgetown Backstreet",        "center": (5.4250, 100.3400), "radius_km": 0.35, "weight": 0.10},
    {"label": "Ipoh Old Town",                "center": (4.5900, 101.0800), "radius_km": 0.30, "weight": 0.08},
    {"label": "Shah Alam Seksyen 7",          "center": (3.0800, 101.5300), "radius_km": 0.4,  "weight": 0.10},
    {"label": "Seremban Bus Terminal",        "center": (2.7250, 101.9450), "radius_km": 0.30, "weight": 0.07},
    {"label": "Melaka Jonker Walk",           "center": (2.1950, 102.2480), "radius_km": 0.25, "weight": 0.08},
    {"label": "Sungai Petani Market",         "center": (5.6470, 100.4880), "radius_km": 0.30, "weight": 0.10},
]

# ─────────────────────────────────────────────────────────────────────────────
# 2.  HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def jitter(lat, lng, radius_km=1.5):
    r = radius_km / 111.0
    angle = random.uniform(0, 2 * math.pi)
    dist  = r * math.sqrt(random.random())
    return round(lat + dist * math.sin(angle), 6), \
           round(lng + dist * math.cos(angle), 6)

def point_in_circle(center_lat, center_lng, radius_km):
    r = radius_km / 111.0
    angle = random.uniform(0, 2 * math.pi)
    dist  = r * math.sqrt(random.random())
    return (round(center_lat + dist * math.sin(angle), 6),
            round(center_lng + dist * math.cos(angle), 6))

def pick_state_district():
    state = random.choice(list(STATES.keys()))
    district_tuple = random.choice(STATES[state]["districts"])
    center = STATES[state]["center"]
    # returns: state, district, city, postcode, center
    return state, district_tuple[0], district_tuple[1], district_tuple[2], center

def uid():
    return str(uuid.uuid4())[:8].upper()

def rand_date(start="2022-01-01", end="2024-12-31"):
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    return (s + timedelta(days=random.randint(0, (e - s).days))).strftime("%Y-%m-%d")

def make_mdc():
    """Simulate a Malaysian Drug Code (NPRA format: MAL + year + 5-digit seq + letter)."""
    year = random.randint(1990, 2023)
    seq  = random.randint(10000, 99999)
    suffix = random.choice(["A","T","X","Z"])
    return f"MAL{year}{seq}{suffix}"

# ─────────────────────────────────────────────────────────────────────────────
# 3.  MEDICINES  (20 items)
#     Columns: medicine_id, name, generic_name, mdc, category,
#              indications, pres_restrictions, dosage,
#              standard_price, tax_rate
# ─────────────────────────────────────────────────────────────────────────────

MEDICINES_RAW = [
    # (brand_name, generic_name, category, indications, pres_restriction, dosage, std_price, tax)
    (
        "Amoxicillin 500mg", "Amoxicillin", "Antibiotic",
        "Bacterial infections of the respiratory tract, urinary tract, skin and soft tissue",
        "Prescription Only",
        "500 mg orally three times daily for 7–10 days",
        8.50, 0.06,
    ),
    (
        "Azithromycin 250mg", "Azithromycin", "Antibiotic",
        "Community-acquired pneumonia, pharyngitis, tonsillitis, skin infections",
        "Prescription Only",
        "500 mg on Day 1, then 250 mg once daily on Days 2–5",
        18.00, 0.06,
    ),
    (
        "Ciprofloxacin 500mg", "Ciprofloxacin", "Antibiotic",
        "Urinary tract infections, lower respiratory tract infections, enteric fever",
        "Prescription Only",
        "500 mg orally twice daily for 7–14 days",
        12.00, 0.06,
    ),
    (
        "Metronidazole 200mg", "Metronidazole", "Antibiotic",
        "Anaerobic bacterial infections, amoebiasis, giardiasis, Helicobacter pylori eradication",
        "Prescription Only",
        "200–400 mg orally three times daily for 7 days",
        6.00, 0.06,
    ),
    (
        "Paracetamol 500mg", "Paracetamol (Acetaminophen)", "Analgesic",
        "Mild to moderate pain relief; fever reduction",
        "Over-the-Counter (OTC)",
        "500–1000 mg every 4–6 hours; max 4 g per day",
        2.50, 0.00,
    ),
    (
        "Ibuprofen 400mg", "Ibuprofen", "Analgesic / NSAID",
        "Pain, inflammation, fever; arthritis, dysmenorrhoea",
        "Over-the-Counter (OTC)",
        "400 mg orally every 6–8 hours with food; max 1200 mg/day (OTC)",
        4.00, 0.00,
    ),
    (
        "Tramadol 50mg", "Tramadol Hydrochloride", "Opioid Analgesic",
        "Moderate to moderately severe acute and chronic pain",
        "Controlled Drug — Schedule C (CD)",
        "50–100 mg orally every 4–6 hours; max 400 mg/day",
        22.00, 0.06,
    ),
    (
        "Oseltamivir 75mg", "Oseltamivir Phosphate", "Antiviral",
        "Treatment and prophylaxis of influenza A and B",
        "Prescription Only",
        "75 mg twice daily for 5 days (treatment); 75 mg once daily for 10 days (prophylaxis)",
        95.00, 0.08,
    ),
    (
        "Acyclovir 200mg", "Acyclovir (Aciclovir)", "Antiviral",
        "Herpes simplex infections, herpes zoster (shingles), varicella (chickenpox)",
        "Prescription Only",
        "200 mg five times daily for 5 days; adjust for renal impairment",
        14.00, 0.06,
    ),
    (
        "Amlodipine 5mg", "Amlodipine Besilate", "Cardiovascular / CCB",
        "Hypertension, stable and vasospastic angina pectoris",
        "Prescription Only",
        "5 mg once daily; may be increased to 10 mg once daily",
        9.00, 0.06,
    ),
    (
        "Metformin 500mg", "Metformin Hydrochloride", "Antidiabetic / Biguanide",
        "Type 2 diabetes mellitus; polycystic ovary syndrome (off-label)",
        "Prescription Only",
        "500 mg twice or three times daily with meals; max 2550 mg/day",
        5.50, 0.06,
    ),
    (
        "Atorvastatin 20mg", "Atorvastatin Calcium", "Cholesterol / Statin",
        "Hypercholesterolaemia, mixed dyslipidaemia, cardiovascular risk reduction",
        "Prescription Only",
        "10–80 mg once daily at any time of day",
        25.00, 0.06,
    ),
    (
        "Omeprazole 20mg", "Omeprazole", "Gastrointestinal / PPI",
        "Peptic ulcer disease, GERD, H. pylori eradication (with antibiotics), Zollinger-Ellison syndrome",
        "Prescription Only",
        "20–40 mg once daily before a meal; 4–8 week course",
        8.00, 0.06,
    ),
    (
        "Loratadine 10mg", "Loratadine", "Antihistamine",
        "Allergic rhinitis, urticaria, hay fever",
        "Over-the-Counter (OTC)",
        "10 mg once daily",
        6.50, 0.00,
    ),
    (
        "Salbutamol 100mcg Inhaler", "Salbutamol Sulphate", "Respiratory / SABA",
        "Acute bronchospasm, asthma, COPD — short-acting bronchodilator (reliever)",
        "Prescription Only",
        "100–200 mcg (1–2 puffs) as needed; max 8 puffs/day",
        18.50, 0.06,
    ),
    (
        "Prednisolone 5mg", "Prednisolone", "Corticosteroid",
        "Inflammatory and allergic conditions, asthma, autoimmune diseases, transplant rejection prevention",
        "Prescription Only",
        "Initial: 5–60 mg/day; taper dose on long-term use",
        12.00, 0.06,
    ),
    (
        "Vitamin C 1000mg", "Ascorbic Acid", "Supplement / Vitamin",
        "Prevention and treatment of Vitamin C deficiency; antioxidant supplementation",
        "Over-the-Counter (OTC)",
        "1000 mg once daily",
        7.00, 0.00,
    ),
    (
        "Vitamin D3 5000IU", "Cholecalciferol", "Supplement / Vitamin",
        "Vitamin D deficiency, osteoporosis prophylaxis, rickets",
        "Over-the-Counter (OTC)",
        "5000 IU once daily; higher doses under medical supervision",
        22.00, 0.00,
    ),
    (
        "Omega-3 1000mg", "Omega-3 Fatty Acids (EPA/DHA)", "Supplement / Nutraceutical",
        "Hypertriglyceridaemia, cardiovascular protection, anti-inflammatory supplementation",
        "Over-the-Counter (OTC)",
        "1000 mg once to three times daily with meals",
        30.00, 0.00,
    ),
    (
        "Sildenafil 50mg", "Sildenafil Citrate", "PDE-5 Inhibitor",
        "Erectile dysfunction; pulmonary arterial hypertension (higher doses)",
        "Prescription Only",
        "50 mg approximately 1 hour before sexual activity; range 25–100 mg",
        55.00, 0.08,
    ),
]

def gen_medicines():
    rows = []
    for (name, generic, cat, indications, pres_restriction, dosage, price, tax) in MEDICINES_RAW:
        rows.append({
            "medicine_id":       f"MED-{uid()}",
            "name":              name,
            "generic_name":      generic,
            "mdc":               make_mdc(),
            "category":          cat,
            "indications":       indications,
            "pres_restrictions": pres_restriction,
            "dosage":            dosage,
            "standard_price":    price,
            "tax_rate":          tax,
        })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT_DIR, "medicines.csv"), index=False)
    print(f"  ✓ medicines.csv          ({len(df)} rows, {len(df.columns)} cols)")
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 4.  SUPPLIERS  (30 total)
# ─────────────────────────────────────────────────────────────────────────────

LEGIT_SUPPLIERS = [
    "Duopharma Biotech Sdn Bhd", "CCM Duopharma Marketing Sdn Bhd",
    "Pharmaniaga Logistics Sdn Bhd", "Hovid Bhd", "Apex Pharmacy Marketing",
    "Caring Pharmacy Group", "KPJ Healthcare Supply", "Alpro Pharmacy Sdn Bhd",
    "Mega Lifesciences (M) Sdn Bhd", "Kotra Pharma Sdn Bhd",
    "Wellesta Holdings Sdn Bhd", "Southern Pharma Distribution",
    "Northern Med Supplies Sdn Bhd", "Eastpoint Pharmaceuticals Sdn Bhd",
    "Medispec (M) Sdn Bhd",
]

SUSPICIOUS_SUPPLIERS = [
    "Best Price Trading (Tiada Lesen)", "MegaDrug Wholesale",
    "FastMed Supply Co.", "CheapRx Distribution", "HealthPlus Traders",
    "UniMed Unregistered Sdn Bhd", "QuickCure Supplies",
    "BudgetPharma Network", "MedXpress Informal", "PharmaGo Borderless",
    "DrugMart Shadow", "NoRegMed Co.", "AltMed Supply Chain",
    "PseudoPharm Holdings", "FakeCure Distribution Sdn Bhd",
]

def gen_suppliers():
    rows = []
    for name in LEGIT_SUPPLIERS:
        state, district, city, postcode, center = pick_state_district()
        lat, lng = jitter(*center, radius_km=8)
        rows.append({
            "supplier_id":   f"SUP-{uid()}",
            "name":          name,
            "lat":           lat,
            "lng":           lng,
            "address":       f"No.{random.randint(1,200)}, Jalan Industri {random.randint(1,20)}, {district}",
            "city":          city,
            "state":         state,
            "postcode":      postcode,
            "license_no":    f"LIC-{random.randint(100000,999999)}",
            "is_suspicious": False,
        })
    for name in SUSPICIOUS_SUPPLIERS:
        state, district, city, postcode, center = pick_state_district()
        lat, lng = jitter(*center, radius_km=5)
        rows.append({
            "supplier_id":   f"SUP-{uid()}",
            "name":          name,
            "lat":           lat,
            "lng":           lng,
            "address":       f"Lot {random.randint(1,50)}, Kawasan {district}",
            "city":          city,
            "state":         state,
            "postcode":      postcode,
            "license_no":    f"UNLICENSED-{random.randint(1000,9999)}" if random.random() > 0.3 else "",
            "is_suspicious": True,
        })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT_DIR, "suppliers.csv"), index=False)
    print(f"  ✓ suppliers.csv          ({len(df)} rows, {len(df.columns)} cols)")
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 5.  FACILITIES  (80 total)
#     Columns: facility_id, name, type, lat, lng,
#              address, city, state, postcode,
#              district, license_no, active
# ─────────────────────────────────────────────────────────────────────────────

FACILITY_PREFIXES = {
    "hospital": [
        "Hospital Kuala Lumpur", "Hospital Sultanah Aminah", "Hospital Pulau Pinang",
        "Hospital Raja Permaisuri Bainun", "Hospital Sultanah Bahiyah",
        "Hospital Tuanku Ja'afar", "Hospital Melaka", "Hospital Sultanah Fatimah",
        "Pantai Hospital", "Gleneagles Hospital", "Prince Court Medical Centre",
        "Sunway Medical Centre", "Columbia Asia Hospital", "KPJ Damansara Specialist",
        "Subang Jaya Medical Centre", "Tropicana Medical Centre",
        "Island Hospital Penang", "Lam Wah Ee Hospital", "Normah Medical Specialist",
        "Fatimah Hospital Ipoh", "Regency Specialist Hospital",
        "Hospital Ampang", "Hospital Serdang", "Selayang Hospital",
        "Hospital Tengku Ampuan Rahimah",
    ],
    "clinic": [
        "Klinik Kesihatan Chow Kit", "Klinik Kesihatan Bangsar",
        "Klinik Kesihatan Kepong", "Klinik Kesihatan Sungai Buloh",
        "Klinik Kesihatan Brickfields", "Klinik Famili Dr. Ahmad",
        "Klinik Dr. Lim & Partners", "Klinik Mediviron Subang",
        "Klinik Primecare Shah Alam", "Klinik Seri Kembangan",
        "Klinik 1Malaysia Klang", "Klinik Komuniti Johor Bahru",
        "Klinik Dr. Rajan Ipoh", "Klinik Nur Kasih Alor Setar",
        "Klinik Ikhlas Georgetown", "Klinik Sri Petaling",
        "Klinik Desa Puchong", "Klinik Sejahtera Seremban",
        "Klinik Rawatan Am Kajang", "Klinik Medikal Melaka",
        "Klinik Dr. Husna & Rakan", "Klinik Pergigian Sentul",
        "Klinik Wanita Ampang", "Klinik Pakar Titiwangsa",
        "Klinik Pratama Wangsa Maju",
    ],
    "pharmacy": [
        "Guardian Pharmacy KLCC", "Watson's Pharmacy Pavilion",
        "Caring Pharmacy Midvalley", "Alpro Pharmacy Subang",
        "Big Pharmacy Shah Alam", "Farmasi Rakyat Johor Bahru",
        "Farmasi Generik Butterworth", "Farmasi Suria Ipoh",
        "Big Pharmacy Seremban", "Guardian Penang Gurney",
        "Watson's Melaka Dataran", "Farmasi Medikal Wangsa Maju",
        "Caring Pharmacy Ampang", "Alpro Kepong",
        "Farmasi Sentosa Kajang", "Farmasi Daya Puchong",
        "Big Pharmacy Alor Setar", "Guardian Pharmacy Sungai Petani",
        "Farmasi Amanah Sepang", "Farmasi Prima Brickfields",
        "Farmasi Sihat Bangsar", "Watson's Pharmacy Bukit Mertajam",
        "Guardian Pharmacy Teluk Intan", "Farmasi Jaya Taiping",
        "Farmasi Mulia Muar", "Farmasi Cahaya Kulai",
        "Farmasi Bestari Langkawi", "Farmasi Aman Nilai",
        "Farmasi Harapan Port Dickson", "Klinik Farmasi Komuniti Klang",
    ],
}

FACILITY_COUNTS = {"hospital": 25, "clinic": 25, "pharmacy": 30}

JALAN_NAMES = ["Utama", "Baru", "Lama", "Maju", "Sejahtera", "Damai",
               "Setia", "Jaya", "Murni", "Indah", "Wawasan", "Harmoni"]

def gen_facilities():
    rows = []
    for ftype, names in FACILITY_PREFIXES.items():
        count = FACILITY_COUNTS[ftype]
        for i in range(count):
            state, district, city, postcode, center = pick_state_district()
            lat, lng = jitter(*center, radius_km=6)
            rows.append({
                "facility_id": f"FAC-{uid()}",
                "name":        names[i % len(names)],
                "type":        ftype,
                "lat":         lat,
                "lng":         lng,
                "address":     f"No.{random.randint(1,300)}, Jalan {random.choice(JALAN_NAMES)} {random.randint(1,20)}",
                "city":        city,
                "state":       state,
                "postcode":    postcode,
                "district":    district,
                "license_no":  f"MOH-{random.randint(100000,999999)}",
                "active":      True,
            })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT_DIR, "facilities.csv"), index=False)
    print(f"  ✓ facilities.csv         ({len(df)} rows, {len(df.columns)} cols)")
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 6.  FACILITY-MEDICINES
# ─────────────────────────────────────────────────────────────────────────────

def gen_facility_medicines(facilities_df, medicines_df, suppliers_df):
    legit_sups = suppliers_df[~suppliers_df["is_suspicious"]]["supplier_id"].tolist()
    susp_sups  = suppliers_df[suppliers_df["is_suspicious"]]["supplier_id"].tolist()
    rows = []
    for _, fac in facilities_df.iterrows():
        stock = medicines_df.sample(n=random.randint(6, 14))
        for _, med in stock.iterrows():
            use_susp = random.random() < 0.10
            supplier_id = random.choice(susp_sups if use_susp else legit_sups)
            listed_price = round(
                med["standard_price"] * random.uniform(0.85, 1.25), 2
            )
            rows.append({
                "facility_id":  fac["facility_id"],
                "medicine_id":  med["medicine_id"],
                "listed_price": listed_price,
                "supplier_id":  supplier_id,
            })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT_DIR, "facility_medicines.csv"), index=False)
    print(f"  ✓ facility_medicines.csv ({len(df)} rows, {len(df.columns)} cols)")
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 7.  COMPLAINTS  (700 total)
# ─────────────────────────────────────────────────────────────────────────────

COMPLAINT_DESCRIPTIONS = [
    "Tablet colour differs from usual; patient experienced no relief.",
    "Capsule dissolves immediately unlike genuine product; suspected counterfeit.",
    "Packaging seal already broken upon purchase.",
    "No improvement after full course; lab test confirmed inactive ingredient.",
    "Unusual smell and texture; patient developed a rash after use.",
    "Blister pack labelling inconsistent with MOH-registered product.",
    "Expiry date appears tampered — original date scratched off.",
    "Medicine purchased from street vendor near the market.",
    "Barcode does not scan; product unverifiable in MOH system.",
    "Patient hospitalised after consumption; batch number not in national registry.",
    "Outer box appeared genuine but inner foil pack had no hologram.",
    "Seller refused to provide receipt; medicine stored without refrigeration.",
    "Multiple neighbours bought same batch; all reported ineffectiveness.",
    "Price was 60% below standard — suspect adulterated product.",
    "Online purchase via Telegram; seller account now deleted.",
]

def gen_complaints(facilities_df, medicines_df, facility_medicines_df):
    rows = []
    fm_by_fac  = facility_medicines_df.groupby("facility_id")["medicine_id"].apply(list).to_dict()
    all_med_ids = medicines_df["medicine_id"].tolist()

    # ── A. Inside-buffer complaints (~35%) ──────────────────────────────────
    sample_facs = facilities_df.sample(n=min(40, len(facilities_df)), replace=True)
    for _, fac in sample_facs.iterrows():
        for _ in range(random.randint(4, 8)):
            lat, lng = jitter(fac["lat"], fac["lng"], radius_km=0.3)
            avail  = fm_by_fac.get(fac["facility_id"], all_med_ids)
            med_id = random.choice(avail)
            med    = medicines_df[medicines_df["medicine_id"] == med_id].iloc[0]
            reported_price = round(med["standard_price"] * random.uniform(0.5, 1.3), 2)
            rows.append({
                "complaint_id":              f"CMP-{uid()}",
                "date":                       rand_date(),
                "lat":                        lat,
                "lng":                        lng,
                "medicine_id":                med_id,
                "purchased_from_facility_id": fac["facility_id"],
                "description":                random.choice(COMPLAINT_DESCRIPTIONS),
                "reported_price":             reported_price,
                "standard_price":             med["standard_price"],
                "estimated_loss":             round(abs(reported_price - med["standard_price"]), 2),
                "verified":                   random.random() < 0.55,
                "district":                   fac["district"],
                "city":                       fac["city"],
                "state":                      fac["state"],
                "postcode":                   fac["postcode"],
            })

    # ── B. Hotspot complaints (~65%) ────────────────────────────────────────
    hotspot_weights = [h["weight"] for h in FRAUD_HOTSPOTS]
    for _ in range(700 - len(rows)):
        hs  = random.choices(FRAUD_HOTSPOTS, weights=hotspot_weights, k=1)[0]
        lat, lng = point_in_circle(*hs["center"], hs["radius_km"])
        med_id   = random.choice(all_med_ids)
        med      = medicines_df[medicines_df["medicine_id"] == med_id].iloc[0]
        reported_price = round(med["standard_price"] * random.uniform(0.3, 0.75), 2)
        state, district, city, postcode, _ = pick_state_district()
        rows.append({
            "complaint_id":              f"CMP-{uid()}",
            "date":                       rand_date(),
            "lat":                        lat,
            "lng":                        lng,
            "medicine_id":                med_id,
            "purchased_from_facility_id": None,
            "description":                random.choice(COMPLAINT_DESCRIPTIONS),
            "reported_price":             reported_price,
            "standard_price":             med["standard_price"],
            "estimated_loss":             round(med["standard_price"] - reported_price + med["standard_price"], 2),
            "verified":                   random.random() < 0.40,
            "district":                   district,
            "city":                       city,
            "state":                      state,
            "postcode":                   postcode,
        })

    df = pd.DataFrame(rows).sample(frac=1).reset_index(drop=True)
    df.to_csv(os.path.join(OUT_DIR, "complaints.csv"), index=False)
    print(f"  ✓ complaints.csv         ({len(df)} rows, {len(df.columns)} cols)")
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 8.  SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(complaints_df, medicines_df):
    total_loss = complaints_df["estimated_loss"].sum()
    verified   = complaints_df["verified"].sum()
    by_state   = complaints_df.groupby("state").size().sort_values(ascending=False)
    med_lookup = medicines_df.set_index("medicine_id")["name"]
    top_meds   = complaints_df["medicine_id"].map(med_lookup).value_counts().head(5)

    print("\n── Dataset Summary ──────────────────────────────────")
    print(f"  Total complaints  : {len(complaints_df)}")
    print(f"  Verified fakes    : {int(verified)}")
    print(f"  Total est. loss   : MYR {total_loss:,.2f}")
    print(f"\n  Complaints by state:")
    for state, cnt in by_state.items():
        print(f"    {state:<25} {cnt}")
    print(f"\n  Top 5 most-faked medicines:")
    for med, cnt in top_meds.items():
        print(f"    {med:<35} {cnt}")
    print("─────────────────────────────────────────────────────\n")

# ─────────────────────────────────────────────────────────────────────────────
# 9.  MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nGenerating MediGuard test data → {os.path.abspath(OUT_DIR)}\n")
    medicines_df          = gen_medicines()
    suppliers_df          = gen_suppliers()
    facilities_df         = gen_facilities()
    facility_medicines_df = gen_facility_medicines(facilities_df, medicines_df, suppliers_df)
    complaints_df         = gen_complaints(facilities_df, medicines_df, facility_medicines_df)
    print_summary(complaints_df, medicines_df)
    print("All done. ✓\n")