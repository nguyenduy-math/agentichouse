"""
generate_data.py
────────────────
Generate 1 000 synthetic Vietnamese BHYT (healthcare insurance) claims
for ML training.  Output: data/sample_claims_1000.csv

Columns match sample_claims.csv PLUS:
    fraud_label          – "legitimate" | "confirmed_fraud"
    llm_risk_score       – 0-100 float
    rule_risk_score      – 0-100 float
    combined_risk_score  – 0-100 float

Fraud distribution: ~70 % legitimate, ~30 % fraud (11 pattern types).
"""

from __future__ import annotations

import csv
import os
import random
from datetime import date, timedelta
from typing import Any

random.seed(42)

# ── Output path ───────────────────────────────────────────────────────────────
OUT_DIR  = os.path.join(os.path.dirname(__file__), "data")
OUT_FILE = os.path.join(OUT_DIR, "sample_claims_1000.csv")
os.makedirs(OUT_DIR, exist_ok=True)

N_RECORDS = 1_000

# ── Vietnamese patient names ──────────────────────────────────────────────────
FIRST_NAMES = [
    "Nguyễn Văn", "Trần Thị", "Lê Văn", "Phạm Thị", "Hoàng Văn",
    "Huỳnh Thị", "Phan Văn", "Vũ Thị", "Võ Văn", "Đặng Thị",
    "Bùi Văn", "Đỗ Thị", "Hồ Văn", "Ngô Thị", "Dương Văn",
    "Lý Thị", "Đinh Văn", "Trịnh Thị", "Tô Văn", "Trương Thị",
]
LAST_NAMES = [
    "An", "Bình", "Châu", "Dũng", "Giang", "Hà", "Hùng", "Khánh",
    "Lan", "Long", "Mai", "Minh", "Nam", "Nga", "Nhung", "Phúc",
    "Quân", "Thảo", "Thanh", "Trang", "Tú", "Tuấn", "Uyên", "Xuân",
    "Yến", "Ánh", "Đức", "Hải", "Hiếu", "Khoa",
]

def random_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


# ── Hospitals / clinics ───────────────────────────────────────────────────────
HOSPITALS = [
    ("BV-01", "Bệnh viện Đa Khoa Tỉnh Thanh Hóa"),
    ("BV-02", "Bệnh viện Phụ Sản Trung Ương"),
    ("BV-03", "Bệnh viện Hữu Nghị Việt Đức"),
    ("BV-04", "Bệnh viện Răng Hàm Mặt Trung Ương"),
    ("BV-05", "Trung Tâm Chẩn Đoán Y Khoa Hà Nội"),
    ("BV-06", "Bệnh viện Bạch Mai"),
    ("BV-07", "Bệnh viện Đa Khoa Trung Ương Cần Thơ"),
    ("BV-08", "Phòng Khám Đa Khoa Minh Đức"),
    ("BV-09", "Bệnh viện Mắt Trung Ương"),
    ("BV-10", "Phòng Khám Đa Khoa Thái Bình"),
    ("BV-11", "Bệnh viện Đa Khoa Tư Nhân Phú Nhuận"),
    ("BV-12", "Bệnh viện Đa Khoa Khu Vực Miền Núi"),
    ("BV-13", "Bệnh viện Phục Hồi Chức Năng Tỉnh"),
    ("BV-14", "Phòng Khám Chuyên Khoa Tim Mạch"),
    ("BV-15", "Phòng Khám Đa Khoa Nam Định"),
    ("BV-16", "Bệnh viện Đa Khoa Khu Vực Duyên Hải"),
    ("BV-17", "Bệnh viện Chợ Rẫy"),
    ("BV-18", "Bệnh viện Đại Học Y Hà Nội"),
    ("BV-19", "Bệnh viện Nhi Trung Ương"),
    ("BV-20", "Bệnh viện K"),
    ("BV-21", "Bệnh viện 108"),
    ("BV-22", "Bệnh viện Đa Khoa Tỉnh Nghệ An"),
    ("BV-23", "Phòng Khám Chuyên Khoa Nội Tiết"),
    ("BV-24", "Bệnh viện Phổi Trung Ương"),
    ("BV-25", "Trung Tâm Y Tế Huyện Bình Chánh"),
    ("BV-26", "Bệnh viện Đa Khoa Quốc Tế Vinmec"),
    ("BV-27", "Bệnh viện FV"),
    ("BV-28", "Phòng Khám Đa Khoa Sài Gòn"),
    ("BV-29", "Bệnh viện Tâm Thần Trung Ương"),
    ("BV-30", "Bệnh viện Da Liễu TP.HCM"),
]

# ── ICD-10 codes by category ──────────────────────────────────────────────────
LEGIT_DIAG = {
    "outpatient": [
        "Z00.0", "Z34.00", "Z34.10", "Z34.30",   # health checks / antenatal
        "J06.9", "J00", "J11.1",                  # URI / flu
        "E11.9", "E11.65", "E14.9",               # diabetes
        "I10", "I11.9",                            # hypertension
        "K01.1", "K02.1",                          # dental
        "H25.11", "H52.1",                         # eye
        "G43.909", "G43.019",                      # migraine
        "M54.5", "M47.816",                        # back pain
        "F32.1", "F41.1",                          # mental health
        "L30.9", "L20.9",                          # skin
        "N39.0", "N30.00",                         # UTI
        "K21.0", "K25.9",                          # GI
    ],
    "inpatient": [
        "K35.80", "K40.90", "K80.20",             # surgical
        "J18.1", "J18.9", "J22",                   # pneumonia
        "I21.09", "I21.19", "I25.10",              # cardiac
        "S72.001A", "S52.501A", "S82.001A",        # fractures
        "C18.9", "C34.10", "C50.919",              # cancer
        "O80", "O68", "O34.219",                   # obstetrics
        "N18.5", "N18.6",                           # renal
        "G35", "G43.909",                           # neuro
        "A41.9", "A15.0",                           # infection / TB
        "D27.9", "D25.9",                           # benign tumors
    ],
    "lab": [
        "Z13.88", "E11.9", "I10", "E03.9",
        "E11.9|I10", "E78.5|E11.9",
        "N18.3", "K72.90", "B18.1",
    ],
}

FRAUD_DIAG = {
    "phantom_billing": ["Z00.0", "J00", "J06.9", "J11.1"],
    "upcoding": ["J18.9", "I21.09", "K35.80", "S72.001A"],
    "unnecessary_hospitalization": ["J02.9", "J06.9", "M54.5", "J11.1"],
    "inflated_costs": ["J18.1", "D27.9", "M54.5", "K01.1"],
    "duplicate_claims": ["I25.10", "E11.9", "G43.909", "I10"],
    "prescription_fraud": ["J00", "J06.9", "G43.909", "F41.1"],
    "excessive_testing": ["Z00.0", "G43.909", "E11.9", "I10"],
    "ghost_patients": ["Z00.0", "J06.9", "E11.9", "I10"],
    "falsified_diagnoses": ["J18.9", "K35.80", "I21.09", "C18.9"],
    "kickbacks": ["Z00.0", "E11.9", "G43.909", "I10"],
    "procedure_splitting": ["I25.10", "G43.909", "E11.9", "M54.5"],
}

# ── Procedure code pools ──────────────────────────────────────────────────────
PROC_POOL = {
    "KT": [f"KT-{i:03d}" for i in range(1, 25)],
    "PT": [f"PT-{i:03d}" for i in range(1, 20)],
    "XN": [f"XN-{i:03d}" for i in range(1, 15)],
    "CĐHA": [f"CĐHA-{i:03d}" for i in range(1, 10)],
    "TH": [f"TH-{i:03d}" for i in range(1, 15)],
    "XT": [f"XT-{i:03d}" for i in range(1, 8)],
}

def pick_procs(pool_keys: list[str], n: int) -> list[str]:
    procs = []
    for k in pool_keys:
        procs.extend(PROC_POOL[k])
    return random.sample(procs, min(n, len(procs)))


# ── Date helpers ──────────────────────────────────────────────────────────────
START_DATE = date(2023, 1, 1)
END_DATE   = date(2025, 12, 31)

def random_date(start: date = START_DATE, end: date = END_DATE) -> date:
    return start + timedelta(days=random.randint(0, (end - start).days))

def fmt(d: date) -> str:
    return d.isoformat()


# ── Risk score helpers ────────────────────────────────────────────────────────
def legit_scores() -> tuple[float, float, float]:
    llm  = round(random.uniform(3, 25), 1)
    rule = round(random.uniform(3, 25), 1)
    combined = round((llm * 0.5 + rule * 0.5) + random.gauss(0, 2), 1)
    combined = max(0, min(100, combined))
    return llm, rule, combined

def fraud_scores(severity: str = "high") -> tuple[float, float, float]:
    if severity == "high":
        llm  = round(random.uniform(70, 98), 1)
        rule = round(random.uniform(65, 95), 1)
    elif severity == "medium":
        llm  = round(random.uniform(50, 75), 1)
        rule = round(random.uniform(45, 72), 1)
    else:
        llm  = round(random.uniform(35, 60), 1)
        rule = round(random.uniform(30, 55), 1)
    combined = round((llm * 0.6 + rule * 0.4) + random.gauss(0, 3), 1)
    combined = max(0, min(100, combined))
    return llm, rule, combined


# ── Narrative templates ───────────────────────────────────────────────────────
LEGIT_NARRATIVES = {
    "outpatient_checkup": [
        "Bệnh nhân đến khám sức khỏe định kỳ. Không có triệu chứng bất thường. Huyết áp {bp} mmHg. Tim phổi bình thường. Tư vấn dinh dưỡng và tái khám sau 6 tháng.",
        "Khám sức khỏe tổng quát, bệnh nhân không có than phiền. Kết quả xét nghiệm trong giới hạn bình thường.",
        "Khám theo dõi bệnh mãn tính. Bệnh nhân tuân thủ điều trị tốt. Tái khám sau 3 tháng.",
    ],
    "outpatient_flu": [
        "Khám viêm đường hô hấp trên. Ho, sổ mũi {days} ngày. Họng sung huyết nhẹ. Kê đơn thuốc hạ sốt, vitamin C. Không có biến chứng.",
        "Bệnh nhân sốt nhẹ {temp}°C, đau họng. Chẩn đoán cảm cúm thông thường. Điều trị triệu chứng, nghỉ ngơi.",
    ],
    "inpatient_surgery": [
        "Bệnh nhân nhập viện với chẩn đoán {dx}. Phẫu thuật thực hiện thành công. Hậu phẫu ổn định. Xuất viện sau {days} ngày.",
        "Phẫu thuật {proc} thực hiện theo kế hoạch. Bệnh nhân dung nạp tốt, không có biến chứng sau mổ.",
    ],
    "lab": [
        "Xét nghiệm máu thường quy theo chỉ định bác sĩ. Kết quả trong giới hạn bình thường.",
        "Kiểm tra định kỳ theo dõi bệnh lý mãn tính. Các chỉ số ổn định.",
        "Xét nghiệm sàng lọc theo yêu cầu. Không phát hiện bất thường đáng kể.",
    ],
}

FRAUD_NARRATIVES = {
    "phantom_billing": [
        "Bệnh nhân đến khám. [Ghi chú nội bộ: hồ sơ tạo tự động]",
        "Khám theo yêu cầu. Không có triệu chứng rõ ràng.",
    ],
    "upcoding": [
        "Bệnh nhân điều trị {mild_dx}. Hồ sơ ghi chẩn đoán nặng hơn để phù hợp mức thanh toán.",
        "Phẫu thuật đơn giản được ghi là phẫu thuật phức tạp đa tầng. Thời gian mổ {mins} phút. Xuất viện cùng ngày.",
    ],
    "unnecessary_hospitalization": [
        "Nhập viện điều trị {dx} nhẹ. Điều trị {days} ngày nội trú. Bệnh nhân đáp ứng tốt với kháng sinh uống đơn giản.",
        "Bệnh nhân có triệu chứng nhẹ, có thể điều trị ngoại trú. Hồ sơ ghi nhập viện {days} ngày.",
    ],
    "inflated_costs": [
        "Bệnh nhân điều trị nội trú. Hồ sơ ghi phòng dịch vụ cao cấp 1 giường đơn ({price:,} VND/ngày x {days} ngày). Thực tế bệnh nhân nằm phòng tập thể.",
        "Chi phí thuốc và vật tư được kê cao hơn thực tế sử dụng.",
    ],
    "duplicate_claims": [
        "Bệnh nhân khám lần {n} cùng đợt điều trị. Không có thay đổi lâm sàng. Kê lại đơn thuốc cũ.",
        "Hồ sơ trùng lặp với yêu cầu thanh toán trước đó.",
    ],
    "prescription_fraud": [
        "{dx}. Kê {n} loại thuốc gồm: {drugs}.",
        "Cảm lạnh thông thường. Kê thuốc cao cấp không cần thiết bao gồm Glutathione truyền tĩnh mạch, Albumin 20%, Collagen peptide nhập khẩu.",
    ],
    "excessive_testing": [
        "Khám sức khỏe định kỳ bình thường. Bệnh nhân khỏe mạnh. Chỉ định {n} loại xét nghiệm và chẩn đoán hình ảnh không cần thiết.",
        "Đau đầu thông thường, đã có chẩn đoán ổn định. Chỉ định chụp CT sọ não {n} lần trong {weeks} tuần.",
    ],
    "ghost_patients": [
        "Bệnh nhân đến khám. [Không có hồ sơ thực tế]",
        "Hồ sơ bệnh nhân ma. Dịch vụ không thực sự được cung cấp.",
    ],
    "falsified_diagnoses": [
        "Bệnh nhân thực tế chỉ có triệu chứng {mild}. Hồ sơ ghi chẩn đoán {severe} để tăng thanh toán.",
        "Chẩn đoán được điều chỉnh sau khi dịch vụ được thực hiện.",
    ],
    "kickbacks": [
        "Bệnh nhân được giới thiệu từ phòng khám liên kết. Chỉ định xét nghiệm và dịch vụ không cần thiết.",
        "Dịch vụ được chỉ định theo hợp đồng hoa hồng với nhà cung cấp dịch vụ.",
    ],
    "procedure_splitting": [
        "Bệnh nhân khám lần 1 đợt điều trị mới. Tiếp tục điều trị ổn định.",
        "Thủ thuật được tách thành nhiều lần trong cùng đợt điều trị để tăng thanh toán.",
    ],
}


# ── Legitimate claim generators ───────────────────────────────────────────────

def gen_legit_outpatient(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=random.randint(1, 3))
    amount   = round(random.uniform(300_000, 5_000_000), -3)

    dx_cat = random.choice(["outpatient", "outpatient", "lab"])
    diag   = random.choice(LEGIT_DIAG[dx_cat if dx_cat != "lab" else "outpatient"])
    procs  = pick_procs(["KT", "XN"], random.randint(1, 4))

    bp   = f"{random.randint(110,135)}/{random.randint(70,90)}"
    temp = round(random.uniform(36.5, 37.2), 1)
    days = random.randint(1, 5)
    narr_tmpl = random.choice(LEGIT_NARRATIVES["outpatient_checkup"] +
                               LEGIT_NARRATIVES["outpatient_flu"])
    narrative = (narr_tmpl
                 .replace("{bp}", bp)
                 .replace("{temp}", str(temp))
                 .replace("{days}", str(days)))

    llm, rule, comb = legit_scores()
    return {
        "claim_id": f"VN-L{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "outpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "legitimate",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_legit_inpatient(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    los      = random.randint(2, 10)
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=los + random.randint(1, 3))
    amount   = round(random.uniform(5_000_000, 80_000_000), -3)

    diag  = random.choice(LEGIT_DIAG["inpatient"])
    procs = pick_procs(["PT", "XN", "CĐHA"], random.randint(2, 6))
    dx_short = diag.split("|")[0]
    narr_tmpl = random.choice(LEGIT_NARRATIVES["inpatient_surgery"])
    narrative = (narr_tmpl
                 .replace("{dx}", dx_short)
                 .replace("{days}", str(los))
                 .replace("{proc}", random.choice(["nội soi", "mổ mở", "can thiệp"])))

    llm, rule, comb = legit_scores()
    return {
        "claim_id": f"VN-L{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "inpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "legitimate",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_legit_lab(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=random.randint(1, 2))
    amount   = round(random.uniform(150_000, 900_000), -3)

    diag  = random.choice(LEGIT_DIAG["lab"])
    procs = pick_procs(["XN"], random.randint(1, 4))
    narrative = random.choice(LEGIT_NARRATIVES["lab"])

    llm, rule, comb = legit_scores()
    return {
        "claim_id": f"VN-L{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "lab",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "legitimate",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


# ── Fraud claim generators ────────────────────────────────────────────────────

def gen_phantom_billing(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=random.randint(1, 5))
    amount   = round(random.uniform(1_000_000, 8_000_000), -3)

    diag  = random.choice(FRAUD_DIAG["phantom_billing"])
    procs = pick_procs(["KT", "XN"], random.randint(2, 5))
    narrative = random.choice(FRAUD_NARRATIVES["phantom_billing"])

    llm, rule, comb = fraud_scores("high")
    return {
        "claim_id": f"VN-F{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "outpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "confirmed_fraud",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_upcoding(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=1)
    # Claim huge amount for a short/simple procedure
    amount   = round(random.uniform(50_000_000, 200_000_000), -3)
    mins     = random.randint(10, 20)

    diag  = random.choice(FRAUD_DIAG["upcoding"])
    procs = pick_procs(["PT", "KT"], random.randint(5, 10))
    narr_tmpl = random.choice(FRAUD_NARRATIVES["upcoding"])
    narrative = narr_tmpl.replace("{mild_dx}", "viêm nhiễm nhẹ").replace("{mins}", str(mins))

    llm, rule, comb = fraud_scores("high")
    return {
        "claim_id": f"VN-F{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "inpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "confirmed_fraud",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_unbundling(idx: int, patient_id: str, hosp: tuple) -> dict:
    """Procedure splitting / unbundling: many small codes instead of one bundled code."""
    prov_id, prov_name = hosp
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=random.randint(1, 3))
    amount   = round(random.uniform(8_000_000, 40_000_000), -3)

    diag  = random.choice(FRAUD_DIAG["procedure_splitting"])
    procs = pick_procs(["KT", "XN", "CĐHA"], random.randint(10, 18))
    narrative = random.choice(FRAUD_NARRATIVES["procedure_splitting"])

    llm, rule, comb = fraud_scores("medium")
    return {
        "claim_id": f"VN-F{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "outpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "confirmed_fraud",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_unnecessary_hospitalization(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    los      = random.randint(7, 20)
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=los + 1)
    amount   = round(random.uniform(15_000_000, 60_000_000), -3)

    diag  = random.choice(FRAUD_DIAG["unnecessary_hospitalization"])
    procs = pick_procs(["KT", "XN"], random.randint(2, 5))
    narr_tmpl = random.choice(FRAUD_NARRATIVES["unnecessary_hospitalization"])
    narrative = narr_tmpl.replace("{dx}", diag).replace("{days}", str(los))

    llm, rule, comb = fraud_scores("high")
    return {
        "claim_id": f"VN-F{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "inpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "confirmed_fraud",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_duplicate_claims(idx: int, patient_id: str, hosp: tuple) -> list[dict]:
    """Returns 2-3 near-identical duplicate claims."""
    prov_id, prov_name = hosp
    svc_date = random_date()
    amount   = round(random.uniform(2_000_000, 8_000_000), -3)
    diag     = random.choice(FRAUD_DIAG["duplicate_claims"])
    procs    = pick_procs(["KT", "XN"], random.randint(2, 4))
    n_dups   = random.randint(2, 3)

    records = []
    for n in range(n_dups):
        sub_date = svc_date + timedelta(days=n + 1)
        narr_tmpl = random.choice(FRAUD_NARRATIVES["duplicate_claims"])
        narrative = narr_tmpl.replace("{n}", str(n + 1))
        llm, rule, comb = fraud_scores("high")
        suffix = "" if n == 0 else chr(ord("A") + n - 1)
        records.append({
            "claim_id": f"VN-F{idx:04d}{suffix}",
            "patient_id": patient_id,
            "provider_id": prov_id,
            "provider_name": prov_name,
            "claim_amount": int(amount),
            "service_date": fmt(svc_date + timedelta(days=n)),
            "submission_date": fmt(sub_date),
            "claim_type": "outpatient",
            "diagnosis_codes": diag,
            "procedure_codes": "|".join(procs),
            "claim_narrative": narrative,
            "fraud_label": "confirmed_fraud",
            "llm_risk_score": llm,
            "rule_risk_score": rule,
            "combined_risk_score": comb,
        })
    return records


def gen_inflated_costs(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    days_rate = random.randint(3, 7)
    price_day = random.choice([2_000_000, 3_000_000, 5_000_000])
    svc_date  = random_date()
    sub_date  = svc_date + timedelta(days=days_rate + 2)
    amount    = round(price_day * days_rate * random.uniform(1.5, 3), -3)

    diag  = random.choice(FRAUD_DIAG["inflated_costs"])
    procs = pick_procs(["KT", "PT", "XN"], random.randint(3, 7))
    narr_tmpl = random.choice(FRAUD_NARRATIVES["inflated_costs"])
    narrative = (narr_tmpl
                 .replace("{price:,}", f"{price_day:,}")
                 .replace("{price}", str(price_day))
                 .replace("{days}", str(days_rate)))

    llm, rule, comb = fraud_scores("medium")
    return {
        "claim_id": f"VN-F{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "inpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "confirmed_fraud",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_kickbacks(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=random.randint(1, 3))
    amount   = round(random.uniform(5_000_000, 25_000_000), -3)

    diag  = random.choice(FRAUD_DIAG["kickbacks"])
    procs = pick_procs(["KT", "XN", "CĐHA"], random.randint(8, 15))
    narrative = random.choice(FRAUD_NARRATIVES["kickbacks"])

    llm, rule, comb = fraud_scores("medium")
    return {
        "claim_id": f"VN-F{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "outpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "confirmed_fraud",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_ghost_patients(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=random.randint(1, 4))
    amount   = round(random.uniform(500_000, 5_000_000), -3)

    diag  = random.choice(FRAUD_DIAG["ghost_patients"])
    procs = pick_procs(["KT"], random.randint(1, 3))
    narrative = random.choice(FRAUD_NARRATIVES["ghost_patients"])

    llm, rule, comb = fraud_scores("high")
    return {
        "claim_id": f"VN-F{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "outpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "confirmed_fraud",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_falsified_diagnoses(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=random.randint(1, 3))
    amount   = round(random.uniform(20_000_000, 120_000_000), -3)

    diag  = random.choice(FRAUD_DIAG["falsified_diagnoses"])
    procs = pick_procs(["PT", "XT", "KT"], random.randint(4, 8))
    narr_tmpl = random.choice(FRAUD_NARRATIVES["falsified_diagnoses"])
    narrative = narr_tmpl.replace("{mild}", "cảm cúm nhẹ").replace("{severe}", diag)

    llm, rule, comb = fraud_scores("high")
    return {
        "claim_id": f"VN-F{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "inpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "confirmed_fraud",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_prescription_fraud(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=1)
    amount   = round(random.uniform(5_000_000, 30_000_000), -3)

    diag  = random.choice(FRAUD_DIAG["prescription_fraud"])
    n_drugs = random.randint(6, 12)
    procs = pick_procs(["TH", "KT"], n_drugs)
    fancy_drugs = ["Augmentin 1g", "Ceftriaxone 1g tiêm", "Dexamethasone",
                   "Albumin 20%", "Glutathione truyền tĩnh mạch",
                   "Collagen peptide nhập khẩu", "Omeprazole 40mg",
                   "Vitamin tổng hợp nhập khẩu", "Immunoglobulin IV",
                   "Plasma tươi đông lạnh", "Erythropoietin"]
    drug_list = ", ".join(random.sample(fancy_drugs, min(n_drugs, len(fancy_drugs))))
    narr_tmpl = random.choice(FRAUD_NARRATIVES["prescription_fraud"])
    narrative = (narr_tmpl
                 .replace("{dx}", diag)
                 .replace("{n}", str(n_drugs))
                 .replace("{drugs}", drug_list))

    llm, rule, comb = fraud_scores("high")
    return {
        "claim_id": f"VN-F{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "outpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "confirmed_fraud",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_excessive_testing(idx: int, patient_id: str, hosp: tuple) -> dict:
    prov_id, prov_name = hosp
    svc_date = random_date()
    sub_date = svc_date + timedelta(days=1)
    amount   = round(random.uniform(10_000_000, 60_000_000), -3)

    diag  = random.choice(FRAUD_DIAG["excessive_testing"])
    procs = pick_procs(["KT", "XN", "CĐHA"], random.randint(15, 22))
    n     = len(procs)
    weeks = random.randint(2, 4)
    narr_tmpl = random.choice(FRAUD_NARRATIVES["excessive_testing"])
    narrative = narr_tmpl.replace("{n}", str(n)).replace("{weeks}", str(weeks))

    llm, rule, comb = fraud_scores("high")
    return {
        "claim_id": f"VN-F{idx:04d}",
        "patient_id": patient_id,
        "provider_id": prov_id,
        "provider_name": prov_name,
        "claim_amount": int(amount),
        "service_date": fmt(svc_date),
        "submission_date": fmt(sub_date),
        "claim_type": "outpatient",
        "diagnosis_codes": diag,
        "procedure_codes": "|".join(procs),
        "claim_narrative": narrative,
        "fraud_label": "confirmed_fraud",
        "llm_risk_score": llm,
        "rule_risk_score": rule,
        "combined_risk_score": comb,
    }


def gen_procedure_splitting(idx: int, patient_id: str, hosp: tuple) -> list[dict]:
    """Split a bundled procedure into multiple separate claims on consecutive days."""
    prov_id, prov_name = hosp
    svc_date = random_date()
    diag     = random.choice(FRAUD_DIAG["procedure_splitting"])
    amount   = round(random.uniform(2_000_000, 6_000_000), -3)
    n_splits = random.randint(2, 4)

    records = []
    for n in range(n_splits):
        sub_date  = svc_date + timedelta(days=n + 1)
        procs     = pick_procs(["KT", "XN"], random.randint(3, 6))
        narrative = random.choice(FRAUD_NARRATIVES["procedure_splitting"])
        llm, rule, comb = fraud_scores("medium")
        suffix = "" if n == 0 else chr(ord("A") + n - 1)
        records.append({
            "claim_id": f"VN-F{idx:04d}{suffix}",
            "patient_id": patient_id,
            "provider_id": prov_id,
            "provider_name": prov_name,
            "claim_amount": int(amount),
            "service_date": fmt(svc_date + timedelta(days=n)),
            "submission_date": fmt(sub_date),
            "claim_type": "outpatient",
            "diagnosis_codes": diag,
            "procedure_codes": "|".join(procs),
            "claim_narrative": narrative,
            "fraud_label": "confirmed_fraud",
            "llm_risk_score": llm,
            "rule_risk_score": rule,
            "combined_risk_score": comb,
        })
    return records


# ── Main generation loop ───────────────────────────────────────────────────────

FRAUD_GENERATORS = [
    ("phantom_billing",              gen_phantom_billing),
    ("upcoding",                     gen_upcoding),
    ("unbundling",                   gen_unbundling),
    ("unnecessary_hospitalization",  gen_unnecessary_hospitalization),
    ("inflated_costs",               gen_inflated_costs),
    ("kickbacks",                    gen_kickbacks),
    ("ghost_patients",               gen_ghost_patients),
    ("falsified_diagnoses",          gen_falsified_diagnoses),
    ("prescription_fraud",           gen_prescription_fraud),
    ("excessive_testing",            gen_excessive_testing),
]

LEGIT_GENERATORS = [
    gen_legit_outpatient,
    gen_legit_outpatient,
    gen_legit_outpatient,
    gen_legit_inpatient,
    gen_legit_lab,
]


def generate_dataset(n: int = N_RECORDS) -> list[dict]:
    records: list[dict] = []
    legit_target  = int(n * 0.70)
    fraud_target  = n - legit_target

    # Patient & provider pools — enough variation for ML learning
    patient_ids  = [f"BN-{1000 + i}" for i in range(300)]
    hosp_choices = HOSPITALS

    # --- Fraud records ---
    fraud_idx = 1
    while len(records) < fraud_target:
        patient_id = random.choice(patient_ids)
        hosp       = random.choice(hosp_choices)

        # Weighted fraud type selection (include multi-record patterns)
        roll = random.random()
        if roll < 0.10:
            # duplicate claims (multi-record)
            new = gen_duplicate_claims(fraud_idx, patient_id, hosp)
            records.extend(new)
        elif roll < 0.18:
            # procedure splitting (multi-record)
            new = gen_procedure_splitting(fraud_idx, patient_id, hosp)
            records.extend(new)
        else:
            name, gen_fn = random.choice(FRAUD_GENERATORS)
            records.append(gen_fn(fraud_idx, patient_id, hosp))
        fraud_idx += 1

        if len(records) >= fraud_target:
            break

    fraud_actual = len(records)

    # --- Legitimate records ---
    legit_idx = 1
    while len(records) < n:
        patient_id = random.choice(patient_ids)
        hosp       = random.choice(hosp_choices)
        gen_fn     = random.choice(LEGIT_GENERATORS)
        records.append(gen_fn(legit_idx, patient_id, hosp))
        legit_idx += 1

    random.shuffle(records)

    # Re-index claim IDs to avoid collisions after shuffle
    for i, rec in enumerate(records, 1):
        prefix = "VN-F" if rec["fraud_label"] == "confirmed_fraud" else "VN-L"
        # Keep suffix if it ends with a letter (duplicate group marker)
        old_id = rec["claim_id"]
        suffix = old_id[-1] if old_id[-1].isalpha() else ""
        rec["claim_id"] = f"{prefix}{i:04d}{suffix}"

    return records


# ── Write CSV ──────────────────────────────────────────────────────────────────

FIELDNAMES = [
    "claim_id", "patient_id", "provider_id", "provider_name",
    "claim_amount", "service_date", "submission_date", "claim_type",
    "diagnosis_codes", "procedure_codes", "claim_narrative",
    "fraud_label", "llm_risk_score", "rule_risk_score", "combined_risk_score",
]


def main():
    print(f"Generating {N_RECORDS} synthetic BHYT claims …")
    records = generate_dataset(N_RECORDS)

    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)

    # Summary
    total  = len(records)
    fraud  = sum(1 for r in records if r["fraud_label"] == "confirmed_fraud")
    legit  = total - fraud
    print(f"✓ Written {total} rows to {OUT_FILE}")
    print(f"  Legitimate:      {legit} ({legit/total*100:.1f}%)")
    print(f"  Confirmed fraud: {fraud} ({fraud/total*100:.1f}%)")
    print("\nSample rows:")
    for r in records[:5]:
        print(f"  {r['claim_id']:<14} {r['fraud_label']:<18} {r['claim_amount']:>12,} VND  "
              f"llm={r['llm_risk_score']}  rule={r['rule_risk_score']}  comb={r['combined_risk_score']}")


if __name__ == "__main__":
    main()
