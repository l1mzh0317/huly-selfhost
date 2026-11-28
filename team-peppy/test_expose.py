"""Unit tests for team-peppy/expose.py."""
import re
import unittest

import expose


PT_WORKSPACE = '11111111-2222-3333-4444-555555555555'
OTHER_WORKSPACE_LOWER = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
OTHER_WORKSPACE_UPPER = 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'
OTHER_WORKSPACE_MIXED = 'aAbBcCdD-1234-5678-90aB-cDeF01234567'

SAMPLE_NGINX = """server {
    listen 80;
    server_name _;
    client_max_body_size 100M;

    location / {
        proxy_pass http://front:8080;
    }
}
"""


class ExposeTest(unittest.TestCase):
    def test_insert_and_idempotent_replace(self) -> None:
        first = expose.update_nginx_config(SAMPLE_NGINX, PT_WORKSPACE)
        self.assertIn(expose.BEGIN_MARKER, first)
        self.assertIn(expose.END_MARKER, first)
        self.assertLess(first.index(expose.END_MARKER), first.index(expose.LOCATION_ANCHOR))

        second = expose.update_nginx_config(first, PT_WORKSPACE)
        self.assertEqual(first, second)
        self.assertEqual(second.count(expose.BEGIN_MARKER), 1)
        self.assertEqual(second.count(expose.END_MARKER), 1)

    def test_replace_existing_legacy_block(self) -> None:
        legacy = SAMPLE_NGINX.replace(
            '    location / {',
            '    # BEGIN TEAM PEPPY\n'
            '    location = /team-peppy { return 302 /files/old/team-peppy/; }\n'
            '    # END TEAM PEPPY\n\n'
            '    location / {',
            1,
        )
        updated = expose.update_nginx_config(legacy, PT_WORKSPACE)
        self.assertNotIn('/files/old/team-peppy/', updated)
        self.assertEqual(updated, expose.update_nginx_config(SAMPLE_NGINX, PT_WORKSPACE))

    def test_renders_pt_prefix_and_multi_workspace_instances_blocks(self) -> None:
        block = expose.build_route(PT_WORKSPACE)
        self.assertIn(
            f'    location = /team-peppy {{ return 302 /files/{PT_WORKSPACE}/team-peppy/; }}',
            block,
        )
        self.assertIn(
            f'    location = /team-peppy/ {{ return 302 /files/{PT_WORKSPACE}/team-peppy/; }}',
            block,
        )
        self.assertIn(f'    location ^~ /files/{PT_WORKSPACE}/team-peppy/ {{', block)
        self.assertIn(
            f'        rewrite ^/files/{PT_WORKSPACE}/team-peppy/(.*)$ /team-peppy/$1 break;',
            block,
        )
        self.assertIn(f'    location ~ "{expose.INSTANCES_PATH_REGEX}" {{', block)
        self.assertIn(
            f'        rewrite "{expose.INSTANCES_PATH_REGEX}" /team-peppy/workspaces/$1$2 break;',
            block,
        )
        # Ensure the regex block appears after the PT prefix block inside the managed section.
        self.assertLess(
            block.index(f'location ^~ /files/{PT_WORKSPACE}/team-peppy/'),
            block.index(f'location ~ "{expose.INSTANCES_PATH_REGEX}"'),
        )

    def test_instances_regex_accepts_valid_paths(self) -> None:
        pattern = re.compile(expose.INSTANCES_PATH_REGEX)
        valid_cases = [
            (
                f'/files/{OTHER_WORKSPACE_LOWER}/team-peppy/api/instances',
                OTHER_WORKSPACE_LOWER,
                '/api/instances',
            ),
            (
                f'/files/{OTHER_WORKSPACE_LOWER}/team-peppy/api/instances/targets',
                OTHER_WORKSPACE_LOWER,
                '/api/instances/targets',
            ),
            (
                f'/files/{OTHER_WORKSPACE_LOWER}/team-peppy/api/instances/connection',
                OTHER_WORKSPACE_LOWER,
                '/api/instances/connection',
            ),
            (
                f'/files/{OTHER_WORKSPACE_UPPER}/team-peppy/api/instances',
                OTHER_WORKSPACE_UPPER,
                '/api/instances',
            ),
            (
                f'/files/{OTHER_WORKSPACE_MIXED}/team-peppy/api/instances/tailnet-policy',
                OTHER_WORKSPACE_MIXED,
                '/api/instances/tailnet-policy',
            ),
        ]
        for path, expected_ws, expected_suffix in valid_cases:
            with self.subTest(path=path):
                match = pattern.match(path)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), expected_ws)
                self.assertEqual(match.group(2), expected_suffix)
                rewritten = f'/team-peppy/workspaces/{match.group(1)}{match.group(2)}'
                self.assertEqual(rewritten, f'/team-peppy/workspaces/{expected_ws}{expected_suffix}')

    def test_instances_regex_rejects_non_instances_and_invalid_paths(self) -> None:
        pattern = re.compile(expose.INSTANCES_PATH_REGEX)
        rejected_paths = [
            f'/files/{OTHER_WORKSPACE_LOWER}/team-peppy/api/tasks',
            f'/files/{OTHER_WORKSPACE_LOWER}/team-peppy/api/route',
            f'/files/{OTHER_WORKSPACE_LOWER}/team-peppy/',
            f'/files/{OTHER_WORKSPACE_LOWER}/team-peppy',
            '/files/not-a-uuid/team-peppy/api/instances',
            f'/files/{OTHER_WORKSPACE_LOWER}/team-peppy/api/instances/../../tasks',
            f'/files/{OTHER_WORKSPACE_LOWER}/team-peppy/api/instances/a/b',
            f'/files/{OTHER_WORKSPACE_LOWER}/team-peppy/api/instances/UPPER',
            f'/files/{OTHER_WORKSPACE_LOWER}/team-peppy/api/instances/',
        ]
        for path in rejected_paths:
            with self.subTest(path=path):
                self.assertIsNone(pattern.match(path))

    def test_build_route_rejects_invalid_workspace_uuid(self) -> None:
        invalid_workspaces = [
            '',
            'not-a-uuid',
            '11111111-2222-3333-4444-55555555555g',
            '11111111-2222-3333-4444-55555555555',
            f'{PT_WORKSPACE}\n',
            f'../{PT_WORKSPACE}',
        ]
        for ws in invalid_workspaces:
            with self.subTest(workspace=ws):
                with self.assertRaises(ValueError):
                    expose.build_route(ws)


if __name__ == '__main__':
    unittest.main()
