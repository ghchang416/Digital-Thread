"""Conservative source-tool grouping before any placeholders or DT nodes exist."""
import hashlib
import json
import re

from src.schemas.creator_els import ElsSourceRow
from .profile import load_profile
from .reader import normalized_name


def group_source_tools(rows: list[ElsSourceRow], *, confirmations=None):
    """Call for ONE selected OP/program only. No cross-workplan sharing or master lookup."""
    profile, _ = load_profile()
    if not 1 <= len(rows) <= profile.limits.maxSteps:
        raise ValueError('ELS_TOOL_SELECTION_LIMIT')
    groups = {}
    seen = set()
    scope = None
    confirmations = confirmations or {}
    if set(confirmations) - {r.rowId for r in rows}:
        raise ValueError('ELS_TOOL_IDENTITY_SCOPE')
    for row in rows:
        if row.rowId in seen or row.table != 'Operation_Machining':
            raise ValueError('ELS_TOOL_ROW_INVALID')
        seen.add(row.rowId)
        values = {normalized_name(k): v for k, v in row.values.items()}
        if len(values) != len(row.values):
            raise ValueError('ELS_TOOL_ROW_INVALID')
        key = tuple(values.get(normalized_name(k)) for k in ('Part_No', 'Part_Rev', 'Op_No', 'PGMNO', 'REVNO'))
        if any(not isinstance(v, str) or not v.strip() for v in key) or (scope is not None and key != scope):
            raise ValueError('ELS_TOOL_SCOPE_MISMATCH')
        scope = key
        source_tag = values.get('toolno')
        if not isinstance(source_tag, str) or not re.fullmatch(r'[Tt]?[0-9]{1,6}', source_tag):
            raise ValueError('ELS_TOOL_TAG_REQUIRED')
        tag = 'T' + str(int(source_tag.lstrip('Tt')))
        identity = {name: {'present': normalized_name(name) in values, 'value': values.get(normalized_name(name))} for name in profile.toolIdentityColumns}
        if not any(item['value'] is not None and item['value'] != '' for item in identity.values()):
            decision = confirmations.get(row.rowId)
            if not decision:
                raise ValueError('ELS_TOOL_IDENTITY_REQUIRED')
            identity = {'manualConfigurationId': decision.configurationId, 'kind': 'explicit-user-confirmation'}
        elif row.rowId in confirmations:
            raise ValueError('ELS_SOURCE_IDENTITY_CANNOT_BE_OVERRIDDEN')
        fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if tag in groups and groups[tag]['fingerprint'] != fingerprint:
            raise ValueError('ELS_TOOL_CONFIGURATION_CONFLICT')
        if tag not in groups:
            groups[tag] = {'toolTag': tag, 'fingerprint': fingerprint, 'rowIds': []}
        groups[tag]['rowIds'].append(row.rowId)
    return list(groups.values())
