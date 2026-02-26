"""
FHIR R4 Bundle Builder
-----------------------
Constructs a valid FHIR R4 Bundle from:
  - Raw MiniMax extraction (for patient PII → hashed)
  - Bedrock standardization output (for ICD-10, drugs, doses)

Output conforms to HL7 FHIR R4 specification.
Patient name is replaced with a SHA-256 derived patient_id.

Resources included:
  - Bundle (collection)
  - Patient (de-identified)
  - Condition (diagnosis with ICD-10)
  - MedicationAdministration × N (one per drug per cycle)
"""

import uuid
from datetime import datetime
from typing import Optional

from pipeline.validator import hash_patient_id


def build_fhir_bundle(
    minimax_extraction: dict,
    standardized: dict,
) -> dict:
    """
    Build a FHIR R4 Bundle from extraction + standardization results.

    Args:
        minimax_extraction: Raw extraction from MiniMax vision agent
        standardized: Standardized output from Bedrock agent

    Returns:
        FHIR R4 Bundle dict (JSON-serializable)
    """
    patient_info = minimax_extraction.get("patient", {})
    name_raw = patient_info.get("name_raw", "UNKNOWN")
    reg_number = patient_info.get("registration_number", "UNKNOWN")

    patient_id = hash_patient_id(name_raw, reg_number)
    bundle_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"

    patient_resource = _build_patient(
        patient_id=patient_id,
        age=patient_info.get("age"),
        sex=patient_info.get("sex"),
        reg_number=reg_number,
    )

    icd10_info = standardized.get("icd10", {})
    condition_id = "condition-" + str(uuid.uuid4())[:8]
    condition_resource = _build_condition(
        condition_id=condition_id,
        patient_id=patient_id,
        icd10_code=icd10_info.get("code", "UNKNOWN"),
        icd10_description=icd10_info.get("description", ""),
        diagnosis_raw=minimax_extraction.get("diagnosis", {}).get("text_raw", ""),
    )

    med_resources = []
    for drug_entry in standardized.get("standardized_drugs", []):
        med_id = "medadmin-" + str(uuid.uuid4())[:8]
        med_resource = _build_medication_administration(
            med_id=med_id,
            patient_id=patient_id,
            condition_id=condition_id,
            drug_standard=drug_entry.get("drug_standard", "UNKNOWN"),
            drug_raw=drug_entry.get("drug_raw", ""),
            dose_mg=drug_entry.get("dose_mg"),
            route=drug_entry.get("route", "IV"),
            diluent=drug_entry.get("diluent"),
            infusion_duration=drug_entry.get("infusion_duration"),
            cycle_id=drug_entry.get("cycle_id", ""),
            date=drug_entry.get("date", ""),
            name_was_corrected=drug_entry.get("name_was_corrected", False),
        )
        med_resources.append(med_resource)

    entries = [
        {"fullUrl": f"urn:uuid:{patient_id}", "resource": patient_resource},
        {"fullUrl": f"urn:uuid:{condition_id}", "resource": condition_resource},
    ] + [
        {"fullUrl": f"urn:uuid:{r['id']}", "resource": r}
        for r in med_resources
    ]

    bundle = {
        "resourceType": "Bundle",
        "id": bundle_id,
        "meta": {
            "lastUpdated": now,
            "tag": [
                {
                    "system": "http://biovault.io/tags",
                    "code": "ai-generated",
                    "display": "AI-extracted from handwritten chart",
                }
            ],
        },
        "type": "collection",
        "timestamp": now,
        "entry": entries,
        "extension": [
            {
                "url": "http://biovault.io/fhir/StructureDefinition/extraction-metadata",
                "extension": [
                    {
                        "url": "sourceDocument",
                        "valueString": "handwritten-chemotherapy-chart",
                    },
                    {
                        "url": "extractionModel",
                        "valueString": "MiniMax-Text-01 + Claude-3-Haiku",
                    },
                    {
                        "url": "hospital",
                        "valueString": minimax_extraction.get("hospital", {}).get("name", ""),
                    },
                    {
                        "url": "unit",
                        "valueString": minimax_extraction.get("hospital", {}).get("unit", ""),
                    },
                    {
                        "url": "regimen",
                        "valueString": minimax_extraction.get("regimen", {}).get("name", ""),
                    },
                    {
                        "url": "overallConfidence",
                        "valueDecimal": minimax_extraction.get("overall_confidence", 0.0),
                    },
                ],
            }
        ],
    }

    return bundle


def _build_patient(
    patient_id: str,
    age: Optional[int],
    sex: Optional[str],
    reg_number: str,
) -> dict:
    gender_map = {"M": "male", "F": "female", "m": "male", "f": "female"}
    gender = gender_map.get(sex, "unknown") if sex else "unknown"

    resource = {
        "resourceType": "Patient",
        "id": patient_id,
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/Patient"],
            "security": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-Confidentiality",
                    "code": "R",
                    "display": "Restricted",
                }
            ],
        },
        "text": {
            "status": "generated",
            "div": f'<div xmlns="http://www.w3.org/1999/xhtml">De-identified Patient: {patient_id}</div>',
        },
        "identifier": [
            {
                "use": "official",
                "system": "http://biovault.io/patient-id",
                "value": patient_id,
            },
            {
                "use": "secondary",
                "system": "http://delta-hospital.bd/registration",
                "value": reg_number,
            },
        ],
        "active": True,
        "gender": gender,
        "extension": [],
    }

    if age is not None:
        resource["extension"].append(
            {
                "url": "http://hl7.org/fhir/StructureDefinition/patient-age",
                "valueAge": {
                    "value": age,
                    "unit": "years",
                    "system": "http://unitsofmeasure.org",
                    "code": "a",
                },
            }
        )

    return resource


def _build_condition(
    condition_id: str,
    patient_id: str,
    icd10_code: str,
    icd10_description: str,
    diagnosis_raw: str,
) -> dict:
    return {
        "resourceType": "Condition",
        "id": condition_id,
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/Condition"],
        },
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                    "display": "Active",
                }
            ]
        },
        "verificationStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                    "code": "confirmed",
                    "display": "Confirmed",
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
                    "system": "http://hl7.org/fhir/sid/icd-10-cm",
                    "code": icd10_code,
                    "display": icd10_description,
                }
            ],
            "text": diagnosis_raw,
        },
        "subject": {
            "reference": f"Patient/{patient_id}",
        },
        "recordedDate": datetime.utcnow().strftime("%Y-%m-%d"),
    }


def _build_medication_administration(
    med_id: str,
    patient_id: str,
    condition_id: str,
    drug_standard: str,
    drug_raw: str,
    dose_mg: Optional[float],
    route: str,
    diluent: Optional[str],
    infusion_duration: Optional[str],
    cycle_id: str,
    date: str,
    name_was_corrected: bool,
) -> dict:
    route_map = {
        "IV": {
            "system": "http://snomed.info/sct",
            "code": "47625008",
            "display": "Intravenous route",
        },
        "PO": {
            "system": "http://snomed.info/sct",
            "code": "26643006",
            "display": "Oral route",
        },
        "IM": {
            "system": "http://snomed.info/sct",
            "code": "78421000",
            "display": "Intramuscular route",
        },
    }

    resource = {
        "resourceType": "MedicationAdministration",
        "id": med_id,
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/MedicationAdministration"],
        },
        "status": "completed",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                    "display": drug_standard,
                }
            ],
            "text": drug_standard,
        },
        "subject": {
            "reference": f"Patient/{patient_id}",
        },
        "context": {
            "reference": f"Condition/{condition_id}",
        },
        "effectiveDateTime": date or datetime.utcnow().strftime("%Y-%m-%d"),
        "note": [
            {"text": f"Cycle: {cycle_id}"},
            {"text": f"Handwritten name: '{drug_raw}'"},
        ],
        "dosage": {
            "route": route_map.get(route.upper() if route else "IV", route_map["IV"]),
        },
        "extension": [
            {
                "url": "http://biovault.io/fhir/StructureDefinition/cycle-id",
                "valueString": cycle_id,
            },
            {
                "url": "http://biovault.io/fhir/StructureDefinition/drug-name-corrected",
                "valueBoolean": name_was_corrected,
            },
        ],
    }

    if dose_mg is not None:
        resource["dosage"]["dose"] = {
            "value": dose_mg,
            "unit": "mg",
            "system": "http://unitsofmeasure.org",
            "code": "mg",
        }

    if diluent:
        resource["dosage"]["text"] = (
            f"In {diluent}" + (f" over {infusion_duration}" if infusion_duration else "")
        )

    return resource
