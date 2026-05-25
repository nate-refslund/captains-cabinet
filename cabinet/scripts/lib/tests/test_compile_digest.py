"""Tests for the learning digest compiler and sanitization pipeline."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from compile_digest_lib import sanitize_text, compile_digest, load_records_from_sample


SAMPLE_CONFIG = {
    'replacements': {
        'Sensed': '[PRODUCT]',
        'Nate': '[CAPTAIN]',
    },
    'patterns': {
        'api_key': r'(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+',
        'env_var': r'(?i)(DATABASE_URL|NEON_|TELEGRAM_BOT_TOKEN)\S*=\S+',
        'bearer_token': r'(?i)bearer\s+[a-zA-Z0-9._\-]+',
        'connection_string': r'(?i)(postgres|postgresql|redis)://[^\s]+',
    },
    'sanitize_urls': True,
    'strip_paths_beyond': '/opt/founders-cabinet',
    'sanitize_external_ids': True,
    'id_patterns': {
        'uuid': r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    },
}


class TestSanitizeText:
    def test_product_name_replaced(self):
        text = "Deployed Sensed v2 to production"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert 'Sensed' not in result
        assert '[PRODUCT]' in result

    def test_captain_name_replaced(self):
        text = "Nate approved the deployment"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert 'Nate' not in result
        assert '[CAPTAIN]' in result

    def test_api_key_redacted(self):
        text = "Used api_key: sk-abc123xyz to authenticate"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert 'sk-abc123xyz' not in result
        assert '[API_KEY]' in result

    def test_env_var_redacted(self):
        text = "Set DATABASE_URL=postgres://user:pass@host/db"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert 'user:pass' not in result
        assert '[ENV_VAR]' in result

    def test_bearer_token_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert 'eyJhbG' not in result
        assert '[BEARER_TOKEN]' in result

    def test_connection_string_redacted(self):
        text = "Connected to postgres://admin:secret@db.neon.tech:5432/mydb"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert 'admin:secret' not in result

    def test_url_sanitized(self):
        text = "Fetched https://api.example.com/v1/users?key=abc123"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert 'key=abc123' not in result
        assert '[URL:api.example.com]' in result

    def test_uuid_sanitized(self):
        text = "Page ID: 331412e2-7cc5-815c-b533-e18353773815"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert '331412e2' not in result
        assert '[ID]' in result

    def test_path_sanitized(self):
        text = "Read /opt/founders-cabinet/instance/config/secret.yml"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert '[PATH]' in result

    def test_plain_text_unchanged(self):
        text = "Fixed a bug in the login flow by adding input validation"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert result == text

    def test_empty_text(self):
        assert sanitize_text('', SAMPLE_CONFIG) == ''
        assert sanitize_text(None, SAMPLE_CONFIG) is None

    def test_multiple_secrets_in_one_text(self):
        text = "Nate set api_key: xyz for Sensed at postgres://u:p@h/d"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert 'Nate' not in result
        assert 'xyz' not in result
        assert 'Sensed' not in result
        assert 'u:p' not in result

    def test_case_insensitive_replacement(self):
        text = "The SENSED app and sensed backend"
        result = sanitize_text(text, SAMPLE_CONFIG)
        assert 'SENSED' not in result
        assert 'sensed' not in result


class TestCompileDigest:
    def test_empty_records(self):
        result = compile_digest([], SAMPLE_CONFIG, '2026-W22')
        assert '2026-W22' in result
        assert 'Source records: 0' in result

    def test_success_records(self):
        records = [
            {
                'task_summary': 'Fixed login bug',
                'officer': 'cto',
                'outcome': 'success',
                'what_happened': 'Patched the auth flow',
                'lessons_learned': 'Always validate tokens on the server side',
            }
        ]
        result = compile_digest(records, SAMPLE_CONFIG, '2026-W22')
        assert '## Successes' in result
        assert 'Fixed login bug' in result
        assert 'Always validate tokens' in result

    def test_failure_records(self):
        records = [
            {
                'task_summary': 'Deploy failed',
                'officer': 'cto',
                'outcome': 'failure',
                'what_happened': 'Build timed out',
                'lessons_learned': 'Set shorter timeouts for CI',
            }
        ]
        result = compile_digest(records, SAMPLE_CONFIG, '2026-W22')
        assert '## Failures' in result

    def test_secrets_stripped_from_digest(self):
        records = [
            {
                'task_summary': 'Connected Sensed to Neon',
                'officer': 'cto',
                'outcome': 'success',
                'what_happened': 'Used DATABASE_URL=postgres://user:pass@host/db',
                'lessons_learned': 'Nate said to use api_key: sk-abc for auth',
            }
        ]
        result = compile_digest(records, SAMPLE_CONFIG, '2026-W22')
        assert 'Sensed' not in result
        assert 'user:pass' not in result
        assert 'sk-abc' not in result
        assert 'Nate' not in result

    def test_key_lessons_section(self):
        records = [
            {
                'task_summary': 'Task A',
                'officer': 'cto',
                'outcome': 'success',
                'lessons_learned': 'Lesson one',
            },
            {
                'task_summary': 'Task B',
                'officer': 'cpo',
                'outcome': 'failure',
                'lessons_learned': 'Lesson two',
            },
        ]
        result = compile_digest(records, SAMPLE_CONFIG, '2026-W22')
        assert '## Key Lessons' in result
        assert '- Lesson one' in result
        assert '- Lesson two' in result

    def test_tags_preserved(self):
        records = [
            {
                'task_summary': 'Something',
                'officer': 'cos',
                'outcome': 'success',
                'tags': ['deploy', 'hotfix'],
            }
        ]
        result = compile_digest(records, SAMPLE_CONFIG)
        assert 'deploy' in result
        assert 'hotfix' in result

    def test_source_count(self):
        records = [{'task_summary': f'Task {i}', 'outcome': 'success'} for i in range(5)]
        result = compile_digest(records, SAMPLE_CONFIG)
        assert 'Source records: 5' in result


class TestLoadSampleData:
    def test_load_list_format(self):
        data = [
            {'task_summary': 'A', 'outcome': 'success'},
            {'task_summary': 'B', 'outcome': 'failure'},
        ]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            records = load_records_from_sample(path)
            assert len(records) == 2
        finally:
            os.unlink(path)

    def test_load_dict_format(self):
        data = {'records': [{'task_summary': 'C', 'outcome': 'partial'}]}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            records = load_records_from_sample(path)
            assert len(records) == 1
        finally:
            os.unlink(path)
