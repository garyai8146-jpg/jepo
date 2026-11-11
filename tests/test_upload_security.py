"""Checks for OAuth storage and upload deduplication.

Run without Streamlit or Google packages by isolating pure Python helpers.
"""
import ast
import hashlib
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app.py"


class UploadSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        functions = {node.name: node for node in cls.tree.body if isinstance(node, ast.FunctionDef)}
        names = ("calculate_local_md5", "reserve_unique_photo")
        body = [functions[name] for name in names]
        namespace = {"hashlib": hashlib}
        exec(compile(ast.Module(body=body, type_ignores=[]), str(SOURCE), "exec"), namespace)
        cls.reserve = staticmethod(namespace["reserve_unique_photo"])

    def test_duplicate_bytes_within_batch_are_skipped(self):
        stored, pending = set(), set()
        self.assertTrue(self.reserve(b"example", stored, pending))
        self.assertFalse(self.reserve(b"example", stored, pending))
        self.assertTrue(self.reserve(b"different", stored, pending))

    def test_existing_drive_file_is_skipped(self):
        digest = hashlib.md5(b"already-uploaded").hexdigest()
        self.assertFalse(self.reserve(b"already-uploaded", {digest}, set()))

    def test_credentials_are_not_written_to_disk(self):
        self.assertNotIn('with open(CONFIG_FILE', self.source)
        self.assertIn('st.session_state["_drive_session_config"]', self.source)
        self.assertIn("LEGACY_CONFIG_FILE", self.source)

    def test_uploaded_credentials_are_not_rendered_in_text_area(self):
        self.assertIn('st.file_uploader("1. 選擇 OAuth 憑證 JSON"', self.source)
        self.assertNotIn('st.text_area("1. 授權憑證內容"', self.source)


if __name__ == "__main__":
    unittest.main()
