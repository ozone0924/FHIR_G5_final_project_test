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

# ── 臨床狀態代碼 ───────────────────────────────────────────────────────────────
CLINICAL_STATUS_CODES = {
    "suspected": "provisional",
    "confirmed": "confirmed",
    "active": "active",
}


def _now_iso() -> str:
    """回傳現在時間的 ISO 8601 字串（UTC）"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


def generate_eicr(patient_data: dict) -> dict:
    """
    產生符合 HL7 eICR 格式的 FHIR R4 Document Bundle JSON。

    Parameters
    ----------
    patient_data : dict
        必要欄位：
            id          (str)  病患唯一識別碼
            name        (str)  姓名
            birthDate   (str)  生日 YYYY-MM-DD
            gender      (str)  male / female / unknown
            disease     (str)  COVID-19 / Dengue / Influenza
            county      (str)  縣市（台北市、新北市…）
            status      (str)  suspected / confirmed
        選填欄位：
            encounter_date (str)  就診時間 ISO 8601，預設為現在
            symptoms       (list) 症狀描述清單
            phone          (str)  聯絡電話

    Returns
    -------
    dict
        FHIR R4 Bundle (type=document) 字典，可直接 json.dumps() 輸出
    """
    pid = patient_data.get("id", _new_uuid())
    disease = patient_data.get("disease", "COVID-19")
    code_info = DISEASE_CODES.get(disease, DISEASE_CODES["COVID-19"])
    status_raw = patient_data.get("status", "suspected")
    encounter_dt = patient_data.get("encounter_date", _now_iso())
    symptoms = patient_data.get("symptoms", ["發燒", "咳嗽"])
    symptoms_text = "、".join(symptoms) if symptoms else "未記載"

    # 各資源 ID
    bundle_id = _new_uuid()
    composition_id = _new_uuid()
    condition_id = _new_uuid()
    observation_id = _new_uuid()
    encounter_id = _new_uuid()
    org_id = "org-tw-cdc"

    bundle = {
        "resourceType": "Bundle",
        "id": bundle_id,
        "meta": {
            "profile": [
                "http://hl7.org/fhir/us/ecr/StructureDefinition/eicr-document-bundle"
            ],
            "lastUpdated": _now_iso(),
        },
        "type": "document",
        "timestamp": _now_iso(),
        "entry": [
            # ── 1. Composition（eICR 主文件頭） ────────────────────────────────
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
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": "55751-2",
                                "display": "Public health case report - PHRI",
                            }
                        ]
                    },
                    "subject": {"reference": f"Patient/{pid}"},
                    "encounter": {"reference": f"Encounter/{encounter_id}"},
                    "date": encounter_dt,
                    "author": [{"reference": f"Organization/{org_id}"}],
                    "title": f"eICR - {disease} 疑似病例通報",
                    "section": [
                        {
                            "title": "Chief Complaint",
                            "code": {
                                "coding": [
                                    {
                                        "system": "http://loinc.org",
                                        "code": "10154-3",
                                        "display": "Chief complaint Narrative",
                                    }
                                ]
                            },
                            "text": {
                                "status": "generated",
                                "div": f"<div xmlns='http://www.w3.org/1999/xhtml'>主訴：{symptoms_text}</div>",
                            },
                        },
                        {
                            "title": "Reportable Conditions",
                            "code": {
                                "coding": [
                                    {
                                        "system": "http://loinc.org",
                                        "code": "55752-0",
                                        "display": "Reportable condition",
                                    }
                                ]
                            },
                            "entry": [{"reference": f"Condition/{condition_id}"}],
                        },
                        {
                            "title": "Results",
                            "code": {
                                "coding": [
                                    {
                                        "system": "http://loinc.org",
                                        "code": "30954-2",
                                        "display": "Relevant diagnostic tests/laboratory data Narrative",
                                    }
                                ]
                            },
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
                    "name": [
                        {
                            "use": "official",
                            "text": patient_data.get("name", "姓名未知"),
                        }
                    ],
                    "birthDate": patient_data.get("birthDate", "1990-01-01"),
                    "gender": patient_data.get("gender", "unknown"),
                    "telecom": [
                        {
                            "system": "phone",
                            "value": patient_data.get("phone", "未提供"),
                            "use": "home",
                        }
                    ]
                    if patient_data.get("phone")
                    else [],
                    "address": [
                        {
                            "use": "home",
                            "district": patient_data.get("county", "台北市"),
                            "country": "TW",
                        }
                    ],
                },
            },
            # ── 3. Condition（通報病例診斷） ────────────────────────────────────
            {
                "fullUrl": f"Condition/{condition_id}",
                "resource": {
                    "resourceType": "Condition",
                    "id": condition_id,
                    "meta": {
                        "profile": [
                            "http://hl7.org/fhir/us/ecr/StructureDefinition/eicr-condition"
                        ]
                    },
                    "clinicalStatus": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                "code": status_raw,
                                "display": status_raw.capitalize(),
                            }
                        ]
                    },
                    "verificationStatus": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                                "code": CLINICAL_STATUS_CODES.get(
                                    status_raw, "provisional"
                                ),
                            }
                        ]
                    },
                    "category": [
                        {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                                    "code": "encounter-diagnosis",
                                    "display": "Encounter Diagnosis",
                                }
                            ]
                        }
                    ],
                    "code": {
                        "coding": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": code_info["snomed"],
                                "display": code_info["display"],
                            }
                        ],
                        "text": disease,
                    },
                    "subject": {"reference": f"Patient/{pid}"},
                    "onsetDateTime": encounter_dt,
                    "recordedDate": _now_iso(),
                },
            },
            # ── 4. Observation（檢驗觀察） ─────────────────────────────────────
            {
                "fullUrl": f"Observation/{observation_id}",
                "resource": {
                    "resourceType": "Observation",
                    "id": observation_id,
                    "status": "preliminary",
                    "category": [
                        {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                    "code": "laboratory",
                                    "display": "Laboratory",
                                }
                            ]
                        }
                    ],
                    "code": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": code_info["loinc_panel"],
                                "display": code_info["loinc_display"],
                            }
                        ],
                        "text": f"{disease} 檢驗",
                    },
                    "subject": {"reference": f"Patient/{pid}"},
                    "effectiveDateTime": encounter_dt,
                    "valueCodeableConcept": {
                        "coding": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": "52101004",
                                "display": "Present",
                            }
                        ],
                        "text": symptoms_text,
                    },
                },
            },
            # ── 5. Encounter（就診紀錄） ────────────────────────────────────────
            {
                "fullUrl": f"Encounter/{encounter_id}",
                "resource": {
                    "resourceType": "Encounter",
                    "id": encounter_id,
                    "status": "finished",
                    "class": {
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                        "code": "AMB",
                        "display": "ambulatory",
                    },
                    "type": [
                        {
                            "coding": [
                                {
                                    "system": "http://snomed.info/sct",
                                    "code": "11429006",
                                    "display": "Consultation",
                                }
                            ]
                        }
                    ],
                    "subject": {"reference": f"Patient/{pid}"},
                    "period": {
                        "start": encounter_dt,
                        "end": encounter_dt,
                    },
                },
            },
            # ── 6. Organization（通報機構：疾管署） ─────────────────────────────
            {
                "fullUrl": f"Organization/{org_id}",
                "resource": {
                    "resourceType": "Organization",
                    "id": org_id,
                    "name": "衛生福利部疾病管制署",
                    "alias": ["Taiwan CDC"],
                    "telecom": [
                        {"system": "url", "value": "https://www.cdc.gov.tw"}
                    ],
                    "address": [
                        {
                            "line": ["林森北路161號"],
                            "city": "台北市",
                            "country": "TW",
                        }
                    ],
                },
            },
        ],
    }

    return bundle


def save_eicr(bundle: dict, output_dir: str = "output") -> str:
    """
    將 eICR Bundle 存成 JSON 檔案。

    Returns
    -------
    str  儲存的完整檔案路徑
    """
    import os

    os.makedirs(output_dir, exist_ok=True)
    bundle_id = bundle.get("id", _new_uuid())
    filename = f"eicr_{bundle_id[:8]}.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)

    return filepath


# ── 獨立執行：產生範例 eICR 並印出 ────────────────────────────────────────────
if __name__ == "__main__":
    sample_patient = {
        "id": "patient-demo-001",
        "name": "王小明",
        "birthDate": "1990-03-15",
        "gender": "male",
        "disease": "COVID-19",
        "county": "台北市",
        "status": "suspected",
        "encounter_date": "2026-05-28T09:30:00Z",
        "symptoms": ["發燒", "咳嗽", "呼吸困難"],
        "phone": "0912-345-678",
    }

    bundle = generate_eicr(sample_patient)
    path = save_eicr(bundle, output_dir="output")
    print(f"✅ eICR 已產生：{path}")
    print(f"   Bundle ID : {bundle['id']}")
    print(f"   病患姓名  : {sample_patient['name']}")
    print(f"   疾病      : {sample_patient['disease']}")
    print(f"   狀態      : {sample_patient['status']}")
    print(f"   條目數    : {len(bundle['entry'])} 個 FHIR resources")
    print()
    print(json.dumps(bundle, ensure_ascii=False, indent=2)[:800], "...")
