"""
程式 B：eICR 產生模組
======================
HL7 Electronic Initial Case Report (eICR) 產生器
依據 HL7 FHIR R4 標準，將病患資料打包成 eICR Document Bundle。

使用方式：
    from eicr_generator import generate_eicr
    bundle = generate_eicr(patient_data)
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional


# ── 疾病 SNOMED-CT 代碼對照表 ──────────────────────────────────────────────────
DISEASE_CODES = {
    "COVID-19": {
        "snomed": "840539006",
        "display": "COVID-19",
        "loinc_panel": "94531-1",
        "loinc_display": "SARS-CoV-2 RNA panel",
    },
    "Dengue": {
        "snomed": "38362002",
        "display": "Dengue fever (disorder)",
        "loinc_panel": "86615-1",
        "loinc_display": "Dengue virus IgM Ab panel",
    },
    "Influenza": {
        "snomed": "57386000",
        "display": "Influenza (disorder)",
        "loinc_panel": "92142-9",
        "loinc_display": "Influenza virus A RNA panel",
    },
}

CLINICAL_STATUS_CODES = {
    "suspected": "provisional",
    "confirmed": "confirmed",
    "active":    "active",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


def generate_eicr(patient_data: dict) -> dict:
    """
    產生符合 HL7 eICR 格式的 FHIR R4 Document Bundle JSON。

    Parameters
    ----------
    patient_data : dict
        必要欄位：id, name, birthDate, gender, disease, county, status
        選填欄位：
            encounter_date (str)  就診時間 ISO 8601（預設：現在）
            report_date    (str)  通報時間 ISO 8601（預設：encounter_date）
            symptoms       (list) 症狀描述清單
            phone          (str)  聯絡電話
            hospital_name  (str)  通報院所名稱
            hospital_address (str) 通報院所地址
            home_address   (str)  病患住家地址
            home_district  (str)  病患住家區域

    Returns
    -------
    dict  FHIR R4 Bundle (type=document)
    """
    pid          = patient_data.get("id", _new_uuid())
    disease      = patient_data.get("disease", "COVID-19")
    code_info    = DISEASE_CODES.get(disease, DISEASE_CODES["COVID-19"])
    status_raw   = patient_data.get("status", "suspected")
    encounter_dt = patient_data.get("encounter_date") or _now_iso()
    # report_date = when the report was filed (after encounter); default = encounter_dt
    report_dt    = patient_data.get("report_date") or encounter_dt
    symptoms     = patient_data.get("symptoms", ["發燒", "咳嗽"])
    symptoms_text = "、".join(symptoms) if symptoms else "未記載"

    hospital_name    = patient_data.get("hospital_name", "通報醫院")
    hospital_address = patient_data.get("hospital_address", "")
    home_address     = patient_data.get("home_address", "")
    home_district    = patient_data.get("home_district", "")
    county           = patient_data.get("county", "台北市")

    # 資源 ID
    bundle_id       = _new_uuid()
    composition_id  = _new_uuid()
    condition_id    = _new_uuid()
    observation_id  = _new_uuid()
    encounter_id    = _new_uuid()
    hospital_org_id = f"org-hosp-{uuid.uuid4().hex[:6]}"
    cdc_org_id      = "org-tw-cdc"

    bundle = {
        "resourceType": "Bundle",
        "id": bundle_id,
        "meta": {
            "profile": [
                "http://hl7.org/fhir/us/ecr/StructureDefinition/eicr-document-bundle"
            ],
            "lastUpdated": report_dt,
        },
        "type": "document",
        "timestamp": report_dt,
        "entry": [
            # ── 1. Composition ────────────────────────────────────────────────
            {
                "fullUrl": f"urn:uuid:{composition_id}",
                "resource": {
                    "resourceType": "Composition",
                    "id": composition_id,
                    "meta": {
                        "profile": [
                            "http://hl7.org/fhir/us/ecr/StructureDefinition/eicr-composition"
                        ]
                    },
                    "status": "preliminary",
                    "type": {
                        "coding": [{
                            "system": "http://loinc.org",
                            "code": "55751-2",
                            "display": "Public health case report - PHRI",
                        }]
                    },
                    "subject":    {"reference": f"Patient/{pid}"},
                    "encounter":  {"reference": f"Encounter/{encounter_id}"},
                    "date":       report_dt,
                    "author":     [{"reference": f"Organization/{hospital_org_id}"}],
                    "custodian":  {"reference": f"Organization/{cdc_org_id}"},
                    "title":      f"eICR - {disease} 疑似病例通報",
                    "section": [
                        {
                            "title": "Chief Complaint",
                            "code": {"coding": [{
                                "system": "http://loinc.org",
                                "code": "10154-3",
                                "display": "Chief complaint Narrative",
                            }]},
                            "text": {
                                "status": "generated",
                                "div": f"<div xmlns='http://www.w3.org/1999/xhtml'>主訴：{symptoms_text}</div>",
                            },
                        },
                        {
                            "title": "Reportable Conditions",
                            "code": {"coding": [{
                                "system": "http://loinc.org",
                                "code": "55752-0",
                                "display": "Reportable condition",
                            }]},
                            "entry": [{"reference": f"Condition/{condition_id}"}],
                        },
                        {
                            "title": "Results",
                            "code": {"coding": [{
                                "system": "http://loinc.org",
                                "code": "30954-2",
                                "display": "Relevant diagnostic tests/laboratory data Narrative",
                            }]},
                            "entry": [{"reference": f"Observation/{observation_id}"}],
                        },
                    ],
                },
            },
            # ── 2. Patient ────────────────────────────────────────────────────
            {
                "fullUrl": f"Patient/{pid}",
                "resource": {
                    "resourceType": "Patient",
                    "id": pid,
                    "name": [{"use": "official", "text": patient_data.get("name", "姓名未知")}],
                    "birthDate": patient_data.get("birthDate", "1990-01-01"),
                    "gender":    patient_data.get("gender", "unknown"),
                    "telecom": ([{
                        "system": "phone",
                        "value":  patient_data["phone"],
                        "use":    "home",
                    }] if patient_data.get("phone") else []),
                    "address": [{
                        "use":      "home",
                        "line":     [home_address] if home_address else [],
                        "district": home_district or county,
                        "city":     county,
                        "country":  "TW",
                    }],
                },
            },
            # ── 3. Condition ──────────────────────────────────────────────────
            {
                "fullUrl": f"Condition/{condition_id}",
                "resource": {
                    "resourceType": "Condition",
                    "id": condition_id,
                    "meta": {"profile": [
                        "http://hl7.org/fhir/us/ecr/StructureDefinition/eicr-condition"
                    ]},
                    "clinicalStatus": {"coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code":   status_raw,
                        "display": status_raw.capitalize(),
                    }]},
                    "verificationStatus": {"coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                        "code":   CLINICAL_STATUS_CODES.get(status_raw, "provisional"),
                    }]},
                    "category": [{"coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                        "code":   "encounter-diagnosis",
                        "display": "Encounter Diagnosis",
                    }]}],
                    "code": {
                        "coding": [{
                            "system":  "http://snomed.info/sct",
                            "code":    code_info["snomed"],
                            "display": code_info["display"],
                        }],
                        "text": disease,
                    },
                    "subject":         {"reference": f"Patient/{pid}"},
                    "onsetDateTime":   encounter_dt,
                    "recordedDate":    report_dt,
                },
            },
            # ── 4. Observation ────────────────────────────────────────────────
            {
                "fullUrl": f"Observation/{observation_id}",
                "resource": {
                    "resourceType": "Observation",
                    "id": observation_id,
                    "status": "preliminary",
                    "category": [{"coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code":   "laboratory",
                        "display": "Laboratory",
                    }]}],
                    "code": {
                        "coding": [{
                            "system":  "http://loinc.org",
                            "code":    code_info["loinc_panel"],
                            "display": code_info["loinc_display"],
                        }],
                        "text": f"{disease} 檢驗",
                    },
                    "subject":           {"reference": f"Patient/{pid}"},
                    "effectiveDateTime": encounter_dt,
                    "valueCodeableConcept": {
                        "coding": [{
                            "system":  "http://snomed.info/sct",
                            "code":    "52101004",
                            "display": "Present",
                        }],
                        "text": symptoms_text,
                    },
                },
            },
            # ── 5. Encounter ──────────────────────────────────────────────────
            {
                "fullUrl": f"Encounter/{encounter_id}",
                "resource": {
                    "resourceType": "Encounter",
                    "id": encounter_id,
                    "status": "finished",
                    "class": {
                        "system":  "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                        "code":    "AMB",
                        "display": "ambulatory",
                    },
                    "type": [{"coding": [{
                        "system":  "http://snomed.info/sct",
                        "code":    "11429006",
                        "display": "Consultation",
                    }]}],
                    "subject":         {"reference": f"Patient/{pid}"},
                    "serviceProvider": {"reference": f"Organization/{hospital_org_id}"},
                    "period": {"start": encounter_dt, "end": encounter_dt},
                },
            },
            # ── 6. Organization — 通報醫療院所 ─────────────────────────────────
            {
                "fullUrl": f"Organization/{hospital_org_id}",
                "resource": {
                    "resourceType": "Organization",
                    "id": hospital_org_id,
                    "type": [{"coding": [{
                        "system":  "http://terminology.hl7.org/CodeSystem/organization-type",
                        "code":    "prov",
                        "display": "Healthcare Provider",
                    }]}],
                    "name": hospital_name,
                    "address": [{
                        "text":    hospital_address,
                        "country": "TW",
                    }] if hospital_address else [],
                },
            },
            # ── 7. Organization — 衛生福利部疾病管制署（custodian） ──────────────
            {
                "fullUrl": f"Organization/{cdc_org_id}",
                "resource": {
                    "resourceType": "Organization",
                    "id": cdc_org_id,
                    "name":  "衛生福利部疾病管制署",
                    "alias": ["Taiwan CDC"],
                    "telecom": [{"system": "url", "value": "https://www.cdc.gov.tw"}],
                    "address": [{
                        "line":    ["林森北路161號"],
                        "city":    "台北市",
                        "country": "TW",
                    }],
                },
            },
        ],
    }

    return bundle


def save_eicr(bundle: dict, output_dir: str = "output") -> str:
    """將 eICR Bundle 存成 JSON 檔案，回傳完整路徑。"""
    import os
    os.makedirs(output_dir, exist_ok=True)
    bundle_id = bundle.get("id", _new_uuid())
    filepath  = os.path.join(output_dir, f"eicr_{bundle_id[:8]}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
    return filepath


# ── 獨立執行：產生範例 eICR ────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import timedelta
    enc_dt = (datetime.now(timezone.utc) - timedelta(days=2, hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rep_dt = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

    sample_patient = {
        "id":               "patient-demo-001",
        "name":             "王小明",
        "birthDate":        "1990-03-15",
        "gender":           "male",
        "disease":          "COVID-19",
        "county":           "台北市",
        "status":           "suspected",
        "encounter_date":   enc_dt,
        "report_date":      rep_dt,
        "symptoms":         ["發燒", "咳嗽", "呼吸困難"],
        "phone":            "0912-345-678",
        "hospital_name":    "台大醫院",
        "hospital_address": "台北市中正區中山南路7號",
        "home_address":     "台北市大安區信義路100號",
        "home_district":    "大安區",
    }

    bundle = generate_eicr(sample_patient)
    path   = save_eicr(bundle, output_dir="output")
    print(f"✅ eICR 已產生：{path}")
    print(f"   Bundle ID  : {bundle['id']}")
    print(f"   病患姓名   : {sample_patient['name']}")
    print(f"   疾病       : {sample_patient['disease']}")
    print(f"   就診時間   : {enc_dt}")
    print(f"   通報時間   : {rep_dt}")
    print(f"   條目數     : {len(bundle['entry'])} 個 FHIR resources")
    print()
    print(json.dumps(bundle, ensure_ascii=False, indent=2)[:1000], "...")
