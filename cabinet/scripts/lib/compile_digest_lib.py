"""Learning digest compilation and sanitization library.

Used by compile-digest.py CLI and by tests.
"""

import glob
import json
import os
import re
from datetime import datetime
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    yaml = None


def load_sanitize_config(config_path=None, product_config_path=None):
    if config_path is None:
        cabinet_root = os.environ.get('CABINET_ROOT', '/opt/founders-cabinet')
        config_path = os.path.join(cabinet_root, 'instance/config/digest-sanitize.yml')

    if not os.path.exists(config_path):
        config = default_config()
    elif yaml is None:
        config = _load_config_without_yaml(config_path)
    else:
        with open(config_path) as f:
            config = yaml.safe_load(f)

    _enrich_from_product_config(config, product_config_path)
    return config


def _enrich_from_product_config(config, product_config_path=None):
    """Read product.yml and add product/captain names as replacement rules."""
    if product_config_path is None:
        cabinet_root = os.environ.get('CABINET_ROOT', '/opt/founders-cabinet')
        product_config_path = os.path.join(cabinet_root, 'instance/config/product.yml')

    if not os.path.exists(product_config_path):
        return

    replacements = config.setdefault('replacements', {})
    try:
        with open(product_config_path) as f:
            text = f.read()
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('name:') and 'product' not in replacements:
                val = line.split(':', 1)[1].strip().strip('"\'')
                if val and val != 'Example Product':
                    replacements[val] = '[PRODUCT]'
            elif line.startswith('captain_name:'):
                val = line.split(':', 1)[1].strip().strip('"\'')
                if val and val != 'Captain':
                    replacements[val] = '[CAPTAIN]'
    except (IOError, OSError):
        pass


def default_config():
    return {
        'replacements': {},
        'patterns': {
            'api_key': r'(?i)(api[_-]?key|token|secret|password|credential)\s*[:=]\s*\S+',
            'env_var': r'(?i)(DATABASE_URL|NEON_|TELEGRAM_|OPENAI_|ANTHROPIC_)\S*=\S+',
            'bearer_token': r'(?i)bearer\s+[a-zA-Z0-9._\-]+',
            'connection_string': r'(?i)(postgres|postgresql|redis|mysql|mongodb)://[^\s]+',
        },
        'sanitize_urls': True,
        'strip_paths_beyond': '/opt/founders-cabinet',
        'sanitize_external_ids': True,
        'id_patterns': {
            'uuid': r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        },
    }


def _load_config_without_yaml(path):
    config = default_config()
    try:
        with open(path) as f:
            text = f.read()
        in_replacements = False
        in_patterns = False
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if stripped.startswith('replacements:'):
                in_replacements = True
                in_patterns = False
                continue
            if stripped.startswith('patterns:'):
                in_patterns = True
                in_replacements = False
                continue
            if not stripped.startswith('-') and ':' in stripped and not line.startswith(' '):
                in_replacements = False
                in_patterns = False
            if (in_replacements or in_patterns) and ':' in stripped:
                key, _, val = stripped.partition(':')
                key = key.strip()
                val = val.strip().strip('\'"')
                if in_replacements:
                    config['replacements'][key] = val
                elif in_patterns:
                    config['patterns'][key] = val
    except Exception:
        pass
    return config


def sanitize_text(text, config):
    if not text:
        return text

    result = text

    for original, replacement in config.get('replacements', {}).items():
        pattern = re.compile(re.escape(original), re.IGNORECASE)
        result = pattern.sub(replacement, result)

    for name, pattern in config.get('patterns', {}).items():
        try:
            result = re.sub(pattern, f'[{name.upper()}]', result)
        except re.error:
            continue

    if config.get('sanitize_urls', True):
        def replace_url(match):
            url = match.group(0)
            try:
                parsed = urlparse(url)
                return f'[URL:{parsed.hostname or "unknown"}]'
            except Exception:
                return '[URL]'
        result = re.sub(r'https?://[^\s\)]+', replace_url, result)

    strip_beyond = config.get('strip_paths_beyond')
    if strip_beyond:
        escaped = re.escape(strip_beyond)
        result = re.sub(
            escaped + r'(/[^\s:,\)]+)',
            lambda m: '[PATH]' + m.group(1),
            result,
        )

    if config.get('sanitize_external_ids', True):
        for name, pattern in config.get('id_patterns', {}).items():
            try:
                result = re.sub(pattern, '[ID]', result)
            except re.error:
                continue

    return result


def load_records_from_logs(log_dir, week=None):
    records = []
    pattern = os.path.join(log_dir, '*.jsonl')
    for filepath in glob.glob(pattern):
        try:
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get('type') == 'experience_record' or 'lessons_learned' in entry:
                            if week:
                                ts = entry.get('timestamp', entry.get('created_at', ''))
                                if ts and not _timestamp_in_week(ts, week):
                                    continue
                            records.append(entry)
                    except json.JSONDecodeError:
                        continue
        except (IOError, OSError):
            continue
    return records


def load_records_from_sample(sample_path):
    with open(sample_path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return data.get('records', [])


def _timestamp_in_week(ts_str, week_str):
    try:
        year, week_num = week_str.split('-W')
        year, week_num = int(year), int(week_num)
        ts = ts_str[:10]
        dt = datetime.strptime(ts, '%Y-%m-%d')
        _, dt_week, _ = dt.isocalendar()
        return dt.year == year and dt_week == week_num
    except (ValueError, AttributeError):
        return True


def compile_digest(records, config, week=None):
    if not records:
        return _format_empty_digest(week)

    sanitized = []
    for record in records:
        entry = {}
        for key in ('task_summary', 'officer', 'outcome', 'what_happened',
                     'lessons_learned', 'tags'):
            val = record.get(key)
            if isinstance(val, str):
                entry[key] = sanitize_text(val, config)
            elif isinstance(val, list):
                entry[key] = [sanitize_text(str(v), config) for v in val]
            elif val is not None:
                entry[key] = val
        sanitized.append(entry)

    week_label = week or _current_week()
    lines = [
        f'# Learning Digest — {week_label}',
        '',
        f'Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}',
        f'Source records: {len(sanitized)}',
        '',
        '---',
        '',
    ]

    by_outcome = {'success': [], 'failure': [], 'partial': [], 'other': []}
    for entry in sanitized:
        outcome = entry.get('outcome', 'other')
        bucket = by_outcome.get(outcome, by_outcome['other'])
        bucket.append(entry)

    if by_outcome['success']:
        lines.append('## Successes')
        lines.append('')
        for entry in by_outcome['success']:
            lines.extend(_format_entry(entry))

    if by_outcome['failure']:
        lines.append('## Failures & Lessons')
        lines.append('')
        for entry in by_outcome['failure']:
            lines.extend(_format_entry(entry))

    if by_outcome['partial']:
        lines.append('## Partial Outcomes')
        lines.append('')
        for entry in by_outcome['partial']:
            lines.extend(_format_entry(entry))

    if by_outcome['other']:
        lines.append('## Other')
        lines.append('')
        for entry in by_outcome['other']:
            lines.extend(_format_entry(entry))

    lessons = []
    for entry in sanitized:
        ll = entry.get('lessons_learned')
        if ll and isinstance(ll, str) and ll.strip():
            lessons.append(ll.strip())
    if lessons:
        lines.append('## Key Lessons')
        lines.append('')
        for lesson in lessons:
            lines.append(f'- {lesson}')
        lines.append('')

    return '\n'.join(lines)


def _format_entry(entry):
    lines = []
    summary = entry.get('task_summary', 'Untitled')
    officer = entry.get('officer', 'unknown')
    lines.append(f'### {summary}')
    lines.append(f'**Officer:** {officer}')
    what = entry.get('what_happened')
    if what:
        lines.append(f'**What happened:** {what}')
    lessons = entry.get('lessons_learned')
    if lessons:
        lines.append(f'**Lesson:** {lessons}')
    tags = entry.get('tags')
    if tags and isinstance(tags, list):
        lines.append(f'**Tags:** {", ".join(tags)}')
    lines.append('')
    return lines


def _format_empty_digest(week=None):
    week_label = week or _current_week()
    return (
        f'# Learning Digest — {week_label}\n\n'
        f'Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}\n'
        f'Source records: 0\n\n'
        f'No experience records found for this period.\n'
    )


def _current_week():
    now = datetime.utcnow()
    _, week, _ = now.isocalendar()
    return f'{now.year}-W{week:02d}'
