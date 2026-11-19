"""Presentation names for curve records; stored identities remain unchanged."""
from calb_sizing_tool.services.curve_release_service import families


_HISTORICAL_NAMES = {
    'SOC20-screenshot-RTE-review-20261118': '18 Nov 2026 · RTE in 5% SOH bands',
    'SOC20-local-review-20261118-r2': '18 Nov 2026 · Original RTE bands (r2)',
    'SOC20-local-review-20261118': '18 Nov 2026 · Initial review',
}


def curve_version_label(release):
    name = release['version_label']
    return _HISTORICAL_NAMES.get(name, name)


def family_label(key):
    try:
        soc, series = key.rsplit('.', 1)
        if not soc.startswith('soc') or series not in ('mean', 'lower_limit'):
            return 'Unavailable condition'
        value = float(soc[3:])
        if not 0 <= value <= 100:
            return 'Unavailable condition'
    except (ValueError, AttributeError):
        return 'Unavailable condition'
    return f"Source SOC {soc[3:]}% · {'Mean' if series == 'mean' else 'Lower limit'}"


def sorted_family_keys(payload):
    def order(key):
        soc, series = key.rsplit('.', 1)
        return float(soc[3:]), 0 if series == 'mean' else 1
    return sorted(families(payload), key=order)


def rte_basis_label(payload):
    rule = payload.get('rte_rule') or {}
    if rule.get('model') == 'screenshot_5pct':
        return '5% SOH bands'
    if rule.get('manual_override'):
        return 'Revised original RTE bands'
    return 'Original RTE bands'
