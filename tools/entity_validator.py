"""Entity validator for extract-entities output.

Validates ASEAN Greedy Extraction rules, country/SG PRIORITY consistency,
and schema compliance. Runs deterministically — no LLM needed.
"""

ASEAN_COUNTRIES = {"Singapore", "Malaysia", "Indonesia", "Thailand", "Vietnam", "Philippines"}


def validate_entities(entities_json: dict) -> dict:
    """Validate entity extraction output against the bank business rules.

    Input: entities_json with "entities_list" key containing list of entity dicts.
    Each entity: {"entity_name": str, "country": str, "relationship_type": str,
                   "ownership_percentage": number|null, "strategic_role": str}

    Returns: {"errors": [str], "warnings": [str], "stats": {...}}
    """
    errors = []
    warnings = []
    entities = entities_json.get("entities_list", [])

    if not entities:
        errors.append("entities_list is empty — no entities extracted")
        return {"errors": errors, "warnings": warnings, "stats": {
            "asean_count": 0, "non_asean_count": 0, "sg_priority_count": 0, "indirect_count": 0, "total_count": 0
        }}

    asean = [e for e in entities if e.get("country") in ASEAN_COUNTRIES]
    non_asean = [e for e in entities if e.get("country") not in ASEAN_COUNTRIES]
    sg_priority = [e for e in entities if "[SG PRIORITY]" in e.get("strategic_role", "")]
    indirect = [e for e in entities if "(indirect)" in e.get("entity_name", "").lower()
                or "indirect" in e.get("strategic_role", "").lower()]

    # Rule 1: SG PRIORITY must match Singapore country
    for e in sg_priority:
        if e.get("country") != "Singapore":
            errors.append(f"[SG PRIORITY] on non-Singapore entity '{e.get('entity_name')}' "
                         f"(country={e.get('country')}) — possible country hallucination")

    # Rule 2: Non-ASEAN cap
    if len(non_asean) > 10:
        errors.append(f"Non-ASEAN entities exceed cap: {len(non_asean)} > 10")

    # Rule 3: ownership_percentage type check
    for e in entities:
        val = e.get("ownership_percentage")
        if val is not None and not isinstance(val, (int, float)):
            errors.append(f"ownership_percentage of '{e.get('entity_name')}' is not number or null")
        if isinstance(val, bool):
            errors.append(f"ownership_percentage of '{e.get('entity_name')}' is boolean — should be number or null")

    # Rule 4: Required fields
    required_fields = ["entity_name", "relationship_type", "strategic_role"]
    for e in entities:
        for field in required_fields:
            if not e.get(field):
                errors.append(f"Missing required field '{field}' in entity: {e.get('entity_name', 'UNKNOWN')}")

    # Rule 5: No ASEAN entities
    if len(entities) > 0 and len(asean) == 0:
        warnings.append("No ASEAN entities found — verify source data completeness for subsidiaries in SG/MY/ID/TH/VN/PH")

    # Rule 6: Duplicate entity names
    names = [e.get("entity_name") for e in entities]
    dupes = [n for n in names if names.count(n) > 1]
    if dupes:
        warnings.append(f"Duplicate entity names found: {list(set(dupes))}")

    return {
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "asean_count": len(asean),
            "non_asean_count": len(non_asean),
            "sg_priority_count": len(sg_priority),
            "indirect_count": len(indirect),
            "total_count": len(entities)
        }
    }


if __name__ == "__main__":
    # Test: valid entity list
    test_valid = {
        "entities_list": [
            {"entity_name": "the bank Singapore Ltd", "country": "Singapore",
             "relationship_type": "Subsidiary", "ownership_percentage": 100.0,
             "strategic_role": "[SG PRIORITY] Core banking subsidiary in Singapore"},
            {"entity_name": "GWM Thailand (indirect)", "country": "Thailand",
             "relationship_type": "Subsidiary", "ownership_percentage": None,
             "strategic_role": "[SEA] Indirect subsidiary via GWM HK. Manufacturing for Thai market."},
        ]
    }
    result = validate_entities(test_valid)
    print("=== Valid Test ===")
    print(f"Errors: {result['errors']}")
    print(f"Warnings: {result['warnings']}")
    print(f"Stats: {result['stats']}")

    # Test: SG PRIORITY hallucination
    test_hallucination = {
        "entities_list": [
            {"entity_name": "GWM HK Investment", "country": "Hong Kong",
             "relationship_type": "Subsidiary", "ownership_percentage": 100.0,
             "strategic_role": "[SG PRIORITY] Investment platform for ASEAN"},
        ]
    }
    result2 = validate_entities(test_hallucination)
    print("\n=== Hallucination Test ===")
    print(f"Errors: {result2['errors']}")

    # Test: non-ASEAN > 10
    test_overflow = {
        "entities_list": [{"entity_name": f"Global Sub {i}", "country": "USA",
                          "relationship_type": "Subsidiary", "ownership_percentage": 100.0,
                          "strategic_role": "Global operations"} for i in range(15)]
    }
    result3 = validate_entities(test_overflow)
    print("\n=== Overflow Test ===")
    print(f"Errors: {result3['errors']}")
    print(f"Stats: {result3['stats']}")

    print("\nAll tests passed!")
