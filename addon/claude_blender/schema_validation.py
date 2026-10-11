"""Dependency-free JSON Schema subset shared by both transport boundaries."""
import difflib
import math

def _schema_types(schema):
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return set(str(item) for item in schema_type)
    if isinstance(schema_type, str):
        return {schema_type}
    return set()


def _matches_json_type(value, schema_type):
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return True


def _integer_schema_value(schema, key):
    value = schema.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _finite_json_number(value):
    return not isinstance(value, float) or math.isfinite(value)


def _accepted_property_hint(key, properties):
    """Name the accepted properties, and the closest one if there is a clear match."""

    if not properties:
        return ""
    accepted = sorted(properties)
    closest = difflib.get_close_matches(str(key), accepted, n=1, cutoff=0.6)
    suggestion = "; did you mean %r?" % closest[0] if closest else ""
    return "%s Accepted: %s" % (suggestion or ".", ", ".join(accepted))


def validate_arguments(value, schema, path="$"):
    """Validate a value against the JSON Schema subset used by this project.

    Dependency-free and bpy-free so both the in-Blender bridge and the
    standalone stdio MCP server can enforce the same tool contract. Returns a
    list of human-readable error strings (empty when valid).
    """

    if not isinstance(schema, dict):
        return []
    errors = []
    schema_types = _schema_types(schema)
    if schema_types and not any(_matches_json_type(value, item) for item in schema_types):
        errors.append(f"{path}: expected {', '.join(sorted(schema_types))}")
        return errors
    if "enum" in schema and value not in schema.get("enum", []):
        errors.append(f"{path}: expected one of {schema.get('enum')}")
        return errors
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not _finite_json_number(value):
            errors.append(f"{path}: expected a finite number")
            return errors
        for keyword, relation in (
            ("minimum", "at least"),
            ("maximum", "at most"),
        ):
            bound = schema.get(keyword)
            if (
                isinstance(bound, (int, float))
                and not isinstance(bound, bool)
                and _finite_json_number(bound)
                and (
                    (keyword == "minimum" and value < bound)
                    or (keyword == "maximum" and value > bound)
                )
            ):
                errors.append(f"{path}: expected {relation} {bound}")
    for combiner in ("anyOf", "oneOf"):
        variants = schema.get(combiner)
        if not isinstance(variants, list):
            continue
        matches = 0
        first_variant_errors = []
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            variant_errors = validate_arguments(value, variant, path)
            if not variant_errors:
                matches += 1
            elif not first_variant_errors:
                first_variant_errors = variant_errors
        if combiner == "anyOf" and matches < 1:
            detail = f"; first variant: {first_variant_errors[0]}" if first_variant_errors else ""
            errors.append(f"{path}: expected to match at least one schema in anyOf{detail}")
        if combiner == "oneOf" and matches != 1:
            errors.append(f"{path}: expected to match exactly one schema in oneOf; matched {matches}")
    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: required property is missing")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    # Naming what is accepted, and the nearest match, turns a
                    # dead end into a one-step correction. A caller that
                    # guessed "domain" for "domains" otherwise learns only
                    # that its guess was wrong, never what to guess next.
                    errors.append(
                        "%s.%s: additional property is not allowed%s"
                        % (path, key, _accepted_property_hint(key, properties))
                    )
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(validate_arguments(value[key], child_schema, f"{path}.{key}"))
    if isinstance(value, list):
        min_items = _integer_schema_value(schema, "minItems")
        max_items = _integer_schema_value(schema, "maxItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} item(s)")
        if max_items is not None and len(value) > max_items:
            errors.append(f"{path}: expected at most {max_items} item(s)")
        if isinstance(schema.get("items"), dict):
            item_schema = schema["items"]
            for index, item in enumerate(value):
                errors.extend(validate_arguments(item, item_schema, f"{path}[{index}]"))
    if isinstance(value, str):
        min_length = _integer_schema_value(schema, "minLength")
        max_length = _integer_schema_value(schema, "maxLength")
        if min_length is not None and len(value) < min_length:
            errors.append(f"{path}: expected at least {min_length} character(s)")
        if max_length is not None and len(value) > max_length:
            errors.append(f"{path}: expected at most {max_length} character(s)")
    return errors
