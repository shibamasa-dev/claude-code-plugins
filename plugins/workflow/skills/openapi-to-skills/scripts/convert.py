"""Convert OpenAPI 3.0 specs to Agent Skills format."""
from __future__ import annotations
import os
import re
import shlex
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader


# ---------------------------------------------------------------------------
# IR (Intermediate Representation) dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ServerDocument:
    url: str
    description: str | None = None


@dataclass
class OAuthFlowDocument:
    name: str
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: dict[str, str] = field(default_factory=dict)


@dataclass
class AuthSchemeDocument:
    name: str
    type: str
    description: str | None = None
    in_: str | None = None
    scheme: str | None = None
    bearer_format: str | None = None
    flows: list[OAuthFlowDocument] = field(default_factory=list)
    openid_connect_url: str | None = None


@dataclass
class SchemaRefDocument:
    ref: str | None = None
    inline: SchemaDocument | None = None


@dataclass
class FieldDocument:
    name: str
    type: str
    required: bool
    description: str | None = None
    schema: SchemaRefDocument | None = None
    nested_fields: list[FieldDocument] | None = None


@dataclass
class SchemaDocument:
    name: str
    type: str  # "object"|"array"|"enum"|"primitive"|"allOf"|"oneOf"|"anyOf"
    description: str | None = None
    fields: list[FieldDocument] | None = None
    enum_values: list | None = None
    composition: list[SchemaRefDocument] | None = None
    items: SchemaRefDocument | None = None


@dataclass
class SchemaGroupDocument:
    prefix: str
    schemas: list[SchemaDocument] = field(default_factory=list)


@dataclass
class SecurityRequirementDocument:
    name: str
    scopes: list[str] = field(default_factory=list)


@dataclass
class ResponseDocument:
    status: str
    description: str
    schema: SchemaRefDocument | None = None


@dataclass
class RequestBodyDocument:
    description: str | None = None
    required: bool = False
    content_types: list[str] = field(default_factory=list)
    schema: SchemaRefDocument | None = None


@dataclass
class ParameterDocument:
    name: str
    in_: str  # "query"|"header"|"path"|"cookie"
    type: str
    required: bool
    description: str | None = None
    schema: SchemaRefDocument | None = None


@dataclass
class OperationDocument:
    operation_id: str
    path: str
    method: str
    tag: str
    summary: str | None = None
    description: str | None = None
    deprecated: bool = False
    parameters: list[ParameterDocument] = field(default_factory=list)
    request_body: RequestBodyDocument | None = None
    responses: list[ResponseDocument] = field(default_factory=list)
    security: list[SecurityRequirementDocument] = field(default_factory=list)


@dataclass
class ResourceDocument:
    tag: str
    description: str | None = None
    operations: list[OperationDocument] = field(default_factory=list)


@dataclass
class SkillMeta:
    name: str
    title: str
    description: str
    version: str
    openapi_version: str
    license: dict[str, str] | None = None
    contact: str | None = None
    servers: list[ServerDocument] = field(default_factory=list)
    security_schemes: list[str] = field(default_factory=list)


@dataclass
class SkillDocument:
    meta: SkillMeta
    resources: list[ResourceDocument] = field(default_factory=list)
    schema_groups: list[SchemaGroupDocument] = field(default_factory=list)
    auth_schemes: list[AuthSchemeDocument] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def to_filename(name: str) -> str:
    """Sanitize a name for use as a filename. Unicode-aware."""
    normalized = unicodedata.normalize("NFC", name)
    sanitized = re.sub(r"[^\w-]+", "-", normalized, flags=re.UNICODE)
    sanitized = re.sub(r"^-+|-+$", "", sanitized)
    sanitized = re.sub(r"-{2,}", "-", sanitized)
    return sanitized or "unnamed"


def extract_schema_prefix(name: str) -> str:
    """Extract prefix from schema name (CamelCase or underscore)."""
    match = re.match(r"^([A-Z][a-z]+)", name)
    if match:
        return match.group(1)
    underscore_match = re.match(r"^([^_]+)", name)
    if underscore_match:
        return underscore_match.group(1)
    return "Other"


def to_skill_name(name: str) -> str:
    """Convert API title to skill name."""
    return to_filename(name).lower()[:64]


# 生成する auth/*.sh に埋め込む値の検証。spec は URL から読めるため信用しない。
# 不正な値は黙って直さず変換を止める（何が埋め込まれたかを利用者が把握できるように）
SCHEME_NAME_RE = re.compile(r"[A-Za-z0-9_.-]+")
AUTH_URL_RE = re.compile(r"https?://[^\s\x00-\x1f]+")  # 値はスクリプトに shlex.quote で入るので、ここでは URL の形と空白・制御文字だけを見る


def validate_scheme_name(name: object) -> None:
    if not isinstance(name, str) or not SCHEME_NAME_RE.fullmatch(name):
        raise ValueError(
            f"securitySchemes のキー名 {name!r} は使えません（英数字と _ . - のみ可）"
        )


def validate_auth_url(scheme_name: str, field_name: str, url: str | None) -> None:
    if url is not None and (not isinstance(url, str) or not AUTH_URL_RE.fullmatch(url)):
        raise ValueError(
            f"securitySchemes.{scheme_name} の {field_name} {url!r} は使えません"
            "（http:// か https:// で始まり、空白・改行を含まない URL のみ可）"
        )


def get_ref_name(ref: str) -> str:
    """Extract the last segment from a $ref path."""
    return ref.rsplit("/", 1)[-1]


def is_reference_object(obj: object) -> bool:
    """Check if an object is a JSON Reference ($ref)."""
    return isinstance(obj, dict) and "$ref" in obj


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HTTP_METHODS = ["get", "put", "post", "delete", "options", "head", "patch", "trace"]


# ---------------------------------------------------------------------------
# Parser functions
# ---------------------------------------------------------------------------

def parse(spec: dict, options: dict | None = None) -> SkillDocument:
    """Main entry point: convert an OpenAPI spec dict into a SkillDocument."""
    options = options or {}
    filter_opts = options.get("filter", {})
    group_by = options.get("group_by", "auto")

    # -n/--name の指定もタイトル由来と同じくファイル名用に無害化する
    skill_name = options.get("skill_name")
    meta = parse_meta(spec, to_filename(skill_name) if skill_name else None)
    resources = parse_resources(spec, filter_opts, group_by)
    schema_groups = parse_schema_groups(spec)
    auth_schemes = parse_auth_schemes(spec)

    return SkillDocument(
        meta=meta,
        resources=resources,
        schema_groups=schema_groups,
        auth_schemes=auth_schemes,
    )


def parse_meta(spec: dict, skill_name: str | None = None) -> SkillMeta:
    """Parse top-level metadata from the spec."""
    info = spec.get("info", {})
    raw_desc = info.get("description")
    description = raw_desc.split("\n")[0][:200] if isinstance(raw_desc, str) else ""

    license_info = info.get("license")
    license_doc = None
    if license_info:
        license_doc = {"name": license_info.get("name", ""), "url": license_info.get("url")}

    contact = info.get("contact", {})
    contact_email = contact.get("email") if isinstance(contact, dict) else None

    servers = [
        ServerDocument(url=s.get("url", ""), description=s.get("description"))
        for s in spec.get("servers", [])
    ]

    components = spec.get("components", {}) or {}
    security_schemes_keys = list((components.get("securitySchemes") or {}).keys())

    return SkillMeta(
        name=skill_name or to_skill_name(info.get("title", "")),
        title=info.get("title", ""),
        description=description,
        version=info.get("version", ""),
        openapi_version=spec.get("openapi", ""),
        license=license_doc,
        contact=contact_email,
        servers=servers,
        security_schemes=security_schemes_keys,
    )


def parse_resources(spec: dict, filter_opts: dict, group_by: str) -> list[ResourceDocument]:
    """Parse all paths/operations into ResourceDocuments grouped by tag or path."""
    tag_descriptions: dict[str, str] = {}
    for tag in spec.get("tags", []):
        tag_descriptions[tag["name"]] = tag.get("description", "")

    resource_map: dict[str, ResourceDocument] = {}

    for path, path_item in spec.get("paths", {}).items():
        if not path_item:
            continue

        if is_path_excluded(path, filter_opts):
            continue

        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not operation:
                continue

            if filter_opts.get("exclude_deprecated") and operation.get("deprecated"):
                continue

            resource_names = get_resource_names(path, operation, group_by)

            for resource_name in resource_names:
                if not is_tag_included(resource_name, filter_opts):
                    continue

                if resource_name not in resource_map:
                    resource_map[resource_name] = ResourceDocument(
                        tag=resource_name,
                        description=tag_descriptions.get(resource_name),
                        operations=[],
                    )

                op_doc = parse_operation(path, method, operation, resource_name)
                resource_map[resource_name].operations.append(op_doc)

    # Sort by operation count descending
    return sorted(resource_map.values(), key=lambda r: len(r.operations), reverse=True)


def get_resource_names(path: str, operation: dict, group_by: str) -> list[str]:
    """Determine resource name(s) for an operation based on groupBy strategy."""
    if group_by == "tags":
        return operation.get("tags") or ["default"]
    elif group_by == "path":
        return [extract_resource_from_path(path)]
    else:  # auto
        tags = operation.get("tags")
        if tags and len(tags) > 0:
            return tags
        return [extract_resource_from_path(path)]


def extract_resource_from_path(path: str) -> str:
    """Extract resource name from path, stripping version prefixes."""
    stripped = re.sub(r"^/(api/)?(v\d+/)?", "/", path, flags=re.IGNORECASE)
    segments = [s for s in stripped.split("/") if s]

    if not segments:
        return "default"

    first = segments[0]
    if first.startswith("{"):
        return "default"

    return first


def parse_operation(path: str, method: str, operation: dict, tag: str) -> OperationDocument:
    """Parse a single operation into an OperationDocument."""
    operation_id = operation.get("operationId") or f"{method}-{path.replace('/', '-')}"

    request_body = None
    if operation.get("requestBody"):
        request_body = parse_request_body(operation["requestBody"])

    return OperationDocument(
        operation_id=operation_id,
        path=path,
        method=method.upper(),
        tag=tag,
        summary=operation.get("summary"),
        description=operation.get("description"),
        deprecated=operation.get("deprecated", False),
        parameters=parse_parameters(operation.get("parameters", [])),
        request_body=request_body,
        responses=parse_responses(operation.get("responses", {})),
        security=parse_security(operation.get("security", [])),
    )


def parse_parameters(params: list) -> list[ParameterDocument]:
    """Parse parameter list, filtering out $ref objects."""
    result = []
    for p in params:
        if is_reference_object(p):
            continue
        schema_ref = parse_schema_ref(p["schema"]) if p.get("schema") else None
        result.append(ParameterDocument(
            name=p["name"],
            in_=p["in"],
            type=get_schema_type(p.get("schema")),
            required=p.get("required", False),
            description=p.get("description"),
            schema=schema_ref,
        ))
    return result


def parse_request_body(req_body: dict) -> RequestBodyDocument | None:
    """Parse a request body. Returns None for $ref objects."""
    if is_reference_object(req_body):
        return None

    content = req_body.get("content", {})
    content_types = list(content.keys())
    first_content_type = content_types[0] if content_types else None
    first_content = content.get(first_content_type) if first_content_type else None

    schema_ref = None
    if first_content and first_content.get("schema"):
        schema_ref = parse_schema_ref(first_content["schema"])

    return RequestBodyDocument(
        description=req_body.get("description"),
        required=req_body.get("required", False),
        content_types=content_types,
        schema=schema_ref,
    )


def parse_responses(responses: dict) -> list[ResponseDocument]:
    """Parse response map into ResponseDocuments."""
    result = []
    for status, response in responses.items():
        if is_reference_object(response):
            result.append(ResponseDocument(status=status, description="(reference)"))
            continue

        content = (response.get("content") or {}).get("application/json")
        schema_ref = None
        if content and content.get("schema"):
            schema_ref = parse_schema_ref(content["schema"])

        result.append(ResponseDocument(
            status=status,
            description=response.get("description", ""),
            schema=schema_ref,
        ))
    return result


def parse_security(security: list) -> list[SecurityRequirementDocument]:
    """Parse security requirements list."""
    result = []
    for req in security:
        for name, scopes in req.items():
            result.append(SecurityRequirementDocument(name=name, scopes=scopes))
    return result


def parse_schema_groups(spec: dict) -> list[SchemaGroupDocument]:
    """Group component schemas by prefix."""
    components = spec.get("components", {}) or {}
    schemas = components.get("schemas")
    if not schemas:
        return []

    groups: dict[str, SchemaGroupDocument] = {}
    for name, schema in schemas.items():
        prefix = extract_schema_prefix(name)
        if prefix not in groups:
            groups[prefix] = SchemaGroupDocument(prefix=prefix, schemas=[])
        groups[prefix].schemas.append(parse_schema(name, schema))

    return list(groups.values())


def parse_schema(name: str, schema: dict) -> SchemaDocument:
    """Parse a schema definition into a SchemaDocument."""
    if is_reference_object(schema):
        return SchemaDocument(name=name, type="object", description=f"Reference: {schema['$ref']}")

    schema_type = get_schema_doc_type(schema)
    doc = SchemaDocument(name=name, type=schema_type, description=schema.get("description"))

    if schema_type == "object" and schema.get("properties"):
        doc.fields = parse_fields(schema)
    elif schema_type == "enum" and schema.get("enum"):
        doc.enum_values = schema["enum"]
    elif schema_type in ("allOf", "oneOf", "anyOf"):
        composite = schema.get("allOf") or schema.get("oneOf") or schema.get("anyOf")
        if composite:
            doc.composition = [parse_schema_ref(item) for item in composite]
    elif schema_type == "array" and schema.get("items"):
        doc.items = parse_schema_ref(schema["items"])

    return doc


def parse_fields(schema: dict) -> list[FieldDocument]:
    """Parse object properties into FieldDocuments."""
    required_set = set(schema.get("required", []))
    fields = []
    for prop_name, prop_schema in (schema.get("properties") or {}).items():
        fields.append(parse_field(prop_name, prop_schema, prop_name in required_set))
    return fields


def parse_field(name: str, schema: dict, is_required: bool) -> FieldDocument:
    """Parse a single field/property."""
    f = FieldDocument(
        name=name,
        type=get_schema_type(schema),
        required=is_required,
    )

    if is_reference_object(schema):
        f.schema = SchemaRefDocument(ref=get_ref_name(schema["$ref"]))
    else:
        f.description = schema.get("description")

        # Nested inline objects
        if schema.get("type") == "object" and schema.get("properties"):
            f.nested_fields = parse_fields(schema)

        # Array of inline objects
        if (
            schema.get("type") == "array"
            and schema.get("items")
            and not is_reference_object(schema["items"])
        ):
            items = schema["items"]
            if items.get("type") == "object" and items.get("properties"):
                f.nested_fields = parse_fields(items)

    return f


def parse_schema_ref(schema: dict) -> SchemaRefDocument:
    """Parse a schema into a SchemaRefDocument (ref, array-of-ref, or inline)."""
    if is_reference_object(schema):
        return SchemaRefDocument(ref=get_ref_name(schema["$ref"]))

    if schema.get("type") == "array" and schema.get("items"):
        if is_reference_object(schema["items"]):
            return SchemaRefDocument(ref=f"{get_ref_name(schema['items']['$ref'])}[]")

    return SchemaRefDocument(inline=parse_schema("(inline)", schema))


def parse_auth_schemes(spec: dict) -> list[AuthSchemeDocument]:
    """Parse component security schemes into AuthSchemeDocuments."""
    components = spec.get("components", {}) or {}
    security_schemes = components.get("securitySchemes")
    if not security_schemes:
        return []

    schemes = []
    for name, scheme in security_schemes.items():
        validate_scheme_name(name)
        if is_reference_object(scheme):
            continue

        doc = AuthSchemeDocument(
            name=name,
            type=scheme["type"],
            description=scheme.get("description"),
        )

        if scheme["type"] == "apiKey":
            doc.in_ = scheme.get("in")
        elif scheme["type"] == "http":
            doc.scheme = scheme.get("scheme")
            doc.bearer_format = scheme.get("bearerFormat")
        elif scheme["type"] == "oauth2":
            doc.flows = parse_oauth_flows(scheme.get("flows"))
            for flow in doc.flows:
                validate_auth_url(name, "authorizationUrl", flow.authorization_url)
                validate_auth_url(name, "tokenUrl", flow.token_url)
        elif scheme["type"] == "openIdConnect":
            doc.openid_connect_url = scheme.get("openIdConnectUrl")
            validate_auth_url(name, "openIdConnectUrl", doc.openid_connect_url)

        schemes.append(doc)

    return schemes


def parse_oauth_flows(flows: dict | None) -> list[OAuthFlowDocument]:
    """Parse OAuth2 flow definitions."""
    if not flows:
        return []

    result = []
    for flow_name, flow in flows.items():
        if not flow or not isinstance(flow, dict):
            continue

        result.append(OAuthFlowDocument(
            name=flow_name,
            authorization_url=flow.get("authorizationUrl") if isinstance(flow.get("authorizationUrl"), str) else None,
            token_url=flow.get("tokenUrl") if isinstance(flow.get("tokenUrl"), str) else None,
            scopes=flow.get("scopes", {}),
        ))

    return result


# ---------------------------------------------------------------------------
# Schema type helpers
# ---------------------------------------------------------------------------

def get_schema_type(schema: object) -> str:
    """Get a human-readable type string for a schema."""
    if not schema:
        return "any"
    if is_reference_object(schema):
        return get_ref_name(schema["$ref"])

    if schema.get("enum"):
        values = schema["enum"]
        display = ", ".join(str(v) for v in values[:3])
        suffix = "..." if len(values) > 3 else ""
        return f"enum: {display}{suffix}"

    if schema.get("type") == "array" and schema.get("items"):
        items = schema["items"]
        if is_reference_object(items):
            return f"{get_ref_name(items['$ref'])}[]"
        return f"{items.get('type', 'any')}[]"

    type_str = schema.get("type", "any")
    if schema.get("format"):
        type_str += f" ({schema['format']})"

    return type_str


def get_schema_doc_type(schema: dict) -> str:
    """Determine the doc-level type classification for a schema."""
    if schema.get("enum"):
        return "enum"
    if schema.get("allOf"):
        return "allOf"
    if schema.get("oneOf"):
        return "oneOf"
    if schema.get("anyOf"):
        return "anyOf"
    if schema.get("type") == "array":
        return "array"
    if schema.get("type") == "object" or schema.get("properties"):
        return "object"
    return "primitive"


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

def is_path_excluded(path: str, filter_opts: dict) -> bool:
    """Check if a path matches any exclude pattern."""
    exclude_paths = filter_opts.get("exclude_paths")
    if not exclude_paths:
        return False
    return any(path == p or path.startswith(p) for p in exclude_paths)


def is_tag_included(tag: str, filter_opts: dict) -> bool:
    """Check if a tag passes inclusion/exclusion filters."""
    include_tags = filter_opts.get("include_tags")
    if include_tags and len(include_tags) > 0:
        return tag in include_tags

    exclude_tags = filter_opts.get("exclude_tags")
    if exclude_tags and len(exclude_tags) > 0:
        return tag not in exclude_tags

    return True


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def needs_token_manager(scheme: AuthSchemeDocument) -> bool:
    """Check if a scheme requires token management (get/refresh)."""
    if scheme.type == "openIdConnect":
        return True
    if scheme.type == "oauth2":
        return any(f.token_url for f in scheme.flows)
    return False


def needs_setup_script(scheme: AuthSchemeDocument) -> bool:
    """Check if a scheme requires credential setup."""
    if scheme.type in ("apiKey", "http", "openIdConnect"):
        return True
    if scheme.type == "oauth2":
        return any(f.token_url for f in scheme.flows)
    return False


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def create_renderer(template_dir: Path | None = None) -> Environment:
    """Create a Jinja2 environment with custom filters."""
    search_path = str(template_dir or TEMPLATES_DIR)
    env = Environment(
        loader=FileSystemLoader(search_path),
        keep_trailing_newline=True,
        lstrip_blocks=False,
    )
    env.filters["to_filename"] = to_filename
    env.filters["extract_schema_prefix"] = extract_schema_prefix
    # .sh テンプレートに spec 由来の値を埋め込むときは必ずこれで引用する
    env.filters["sh_quote"] = lambda v: shlex.quote(str(v))
    return env


def render(doc: SkillDocument, env: Environment) -> dict[str, str]:
    """Render SkillDocument to {relative_path: markdown_content} dict."""
    files: dict[str, str] = {}
    skill_name = doc.meta.name

    # Auth flags
    has_setup = any(needs_setup_script(s) for s in doc.auth_schemes) if doc.auth_schemes else False
    has_token_mgr = any(needs_token_manager(s) for s in doc.auth_schemes) if doc.auth_schemes else False

    # SKILL.md
    total_ops = sum(len(r.operations) for r in doc.resources)
    total_schemas = sum(len(g.schemas) for g in doc.schema_groups)
    tmpl = env.get_template("skill.md.j2")
    files[f"{skill_name}/SKILL.md"] = tmpl.render(
        meta=doc.meta, resources=doc.resources,
        schema_groups=doc.schema_groups, total_ops=total_ops,
        total_schemas=total_schemas,
        has_setup_script=has_setup,
        has_token_manager=has_token_mgr,
    )

    # Resources + Operations
    for resource in doc.resources:
        fname = to_filename(resource.tag)
        tmpl = env.get_template("resource.md.j2")
        files[f"{skill_name}/references/resources/{fname}.md"] = tmpl.render(
            tag=resource.tag, description=resource.description,
            operations=resource.operations,
        )
        for op in resource.operations:
            op_fname = to_filename(op.operation_id)
            tmpl = env.get_template("operation.md.j2")
            files[f"{skill_name}/references/operations/{op_fname}.md"] = tmpl.render(
                method=op.method, path=op.path, tag=op.tag,
                summary=op.summary, description=op.description,
                operation_id=op.operation_id, deprecated=op.deprecated,
                parameters=op.parameters, request_body=op.request_body,
                responses=op.responses, security=op.security,
            )

    # Schema groups
    for group in doc.schema_groups:
        prefix_dir = to_filename(group.prefix)
        tmpl = env.get_template("schema_index.md.j2")
        files[f"{skill_name}/references/schemas/{prefix_dir}/_index.md"] = tmpl.render(
            prefix=group.prefix, schemas=group.schemas,
        )
        for schema in group.schemas:
            tmpl = env.get_template("schema.md.j2")
            files[f"{skill_name}/references/schemas/{prefix_dir}/{to_filename(schema.name)}.md"] = tmpl.render(
                name=schema.name, type=schema.type, description=schema.description,
                fields=schema.fields, enum_values=schema.enum_values,
                composition=schema.composition, items=schema.items,
            )

    # Authentication
    if doc.auth_schemes:
        tmpl = env.get_template("authentication.md.j2")
        files[f"{skill_name}/references/authentication.md"] = tmpl.render(
            schemes=doc.auth_schemes,
        )

    # Auth scripts
    if doc.auth_schemes:
        setup_schemes = [s for s in doc.auth_schemes if needs_setup_script(s)]
        token_schemes = [s for s in doc.auth_schemes if needs_token_manager(s)]

        if setup_schemes:
            tmpl = env.get_template("setup.sh.j2")
            files[f"{skill_name}/auth/setup.sh"] = tmpl.render(
                skill_name=skill_name,
                schemes=setup_schemes,
            )

        if token_schemes:
            token_scheme_info = []
            for s in token_schemes:
                token_url = None
                if s.type == "oauth2":
                    for f in s.flows:
                        if f.token_url:
                            token_url = f.token_url
                            break
                token_scheme_info.append({
                    "name": s.name,
                    "token_url": token_url,
                    "openid_connect_url": s.openid_connect_url,
                })
            tmpl = env.get_template("token-manager.sh.j2")
            files[f"{skill_name}/auth/token-manager.sh"] = tmpl.render(
                skill_name=skill_name,
                schemes=token_scheme_info,
            )

    return files


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def write_files(files: dict[str, str], output_dir: str, force: bool = False) -> None:
    """Write rendered files to the filesystem."""
    # Check if any skill directory already exists (check once per skill name)
    checked_dirs: set[str] = set()
    for rel_path in files:
        skill_dir_name = rel_path.split("/")[0]
        skill_dir = os.path.join(output_dir, skill_dir_name)
        if skill_dir not in checked_dirs:
            checked_dirs.add(skill_dir)
            if os.path.isdir(skill_dir) and not force:
                print(f"Error: Output directory already exists: {skill_dir}", file=sys.stderr)
                print("Use --force to overwrite.", file=sys.stderr)
                sys.exit(1)

    for rel_path, content in files.items():
        full_path = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        if full_path.endswith(".sh"):
            os.chmod(full_path, 0o755)

    # Print summary
    skill_name = next(iter(files)).split("/")[0]
    print(f"Generated {len(files)} files to {os.path.join(output_dir, skill_name)}")


def load_spec(source: str) -> dict:
    """Load an OpenAPI spec from a file path or URL."""
    if source.startswith("http://") or source.startswith("https://"):
        import requests
        resp = requests.get(source, timeout=30)
        resp.raise_for_status()
        return yaml.safe_load(resp.text)

    with open(source, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert OpenAPI 3.0 spec to Agent Skills format"
    )
    parser.add_argument("input", help="OpenAPI spec file path or URL")
    parser.add_argument(
        "-o", "--output",
        default=os.path.expanduser("~/.claude/skills"),
        help="Output directory (default: ~/.claude/skills/)",
    )
    parser.add_argument("-n", "--name", help="Skill name override")
    parser.add_argument("--include-tags", help="Only include these tags (comma-separated)")
    parser.add_argument("--exclude-tags", help="Exclude these tags (comma-separated)")
    parser.add_argument("--exclude-paths", help="Exclude paths starting with these prefixes (comma-separated)")
    parser.add_argument("--exclude-deprecated", action="store_true", help="Exclude deprecated operations")
    parser.add_argument("-g", "--group-by", choices=["tags", "path", "auto"], default="auto")
    parser.add_argument("-f", "--force", action="store_true", help="Overwrite existing output")

    args = parser.parse_args()

    options = {
        "skill_name": args.name,
        "group_by": args.group_by,
        "filter": {
            "include_tags": args.include_tags.split(",") if args.include_tags else None,
            "exclude_tags": args.exclude_tags.split(",") if args.exclude_tags else None,
            "exclude_paths": args.exclude_paths.split(",") if args.exclude_paths else None,
            "exclude_deprecated": args.exclude_deprecated,
        },
    }

    try:
        spec = load_spec(args.input)
        doc = parse(spec, options)
        env = create_renderer()
        files = render(doc, env)
        write_files(files, args.output, force=args.force)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
