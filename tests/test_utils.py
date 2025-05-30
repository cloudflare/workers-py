import json
import os
import tempfile
import tomllib
from pathlib import Path
import unittest
from unittest import mock

import pytest
import commentjson

from pywrangler.utils import get_vendor_path_from_wrangler_config


class TestGetVendorPathFromWranglerConfig(unittest.TestCase):
    """Test the get_vendor_path_from_wrangler_config function."""

    def setUp(self):
        """Set up temporary directory for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up temporary directory after each test."""
        self.temp_dir.cleanup()

    def test_toml_config(self):
        """Test getting vendor path from a TOML configuration."""
        # Create test wrangler.toml
        config_content = {"main": "src/worker.js"}
        config_path = self.project_path / "wrangler.toml"
        
        with open(config_path, "w", encoding="utf-8") as f:
            # Create valid TOML format manually since we can't depend on a TOML writer
            f.write(f'main = "{config_content["main"]}"\n')
        
        # Expected vendor path
        expected_path = Path("src/vendor")
        
        # Call the function
        result = get_vendor_path_from_wrangler_config(self.project_path)
        
        # Assert the result
        self.assertEqual(result, expected_path)

    def test_jsonc_config(self):
        """Test getting vendor path from a JSONC configuration."""
        # Create test wrangler.jsonc
        config_content = {"main": "dist/index.js"}
        config_path = self.project_path / "wrangler.jsonc"
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_content, f)
        
        # Expected vendor path
        expected_path = Path("dist/vendor")
        
        # Call the function
        result = get_vendor_path_from_wrangler_config(self.project_path)
        
        # Assert the result
        self.assertEqual(result, expected_path)

    def test_nested_path(self):
        """Test getting vendor path from a configuration with nested path."""
        # Create test wrangler.toml
        config_content = {"main": "src/backend/api/worker.js"}
        config_path = self.project_path / "wrangler.toml"
        
        with open(config_path, "w", encoding="utf-8") as f:
            # Create valid TOML format manually since we can't depend on a TOML writer
            f.write(f'main = "{config_content["main"]}"\n')
        
        # Expected vendor path
        expected_path = Path("src/backend/api/vendor")
        
        # Call the function
        result = get_vendor_path_from_wrangler_config(self.project_path)
        
        # Assert the result
        self.assertEqual(result, expected_path)

    def test_no_config_files(self):
        """Test error when no configuration files exist."""
        with self.assertRaises(FileNotFoundError) as context:
            get_vendor_path_from_wrangler_config(self.project_path)
        
        self.assertIn("not found", str(context.exception))

    def test_invalid_toml(self):
        """Test error when TOML file is invalid."""
        # Create invalid wrangler.toml
        config_path = self.project_path / "wrangler.toml"
        
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("invalid toml content =")
        
        with self.assertRaises(ValueError) as context:
            get_vendor_path_from_wrangler_config(self.project_path)
        
        self.assertIn("Invalid TOML", str(context.exception))

    def test_invalid_jsonc(self):
        """Test error when JSONC file is invalid."""
        # Create invalid wrangler.jsonc
        config_path = self.project_path / "wrangler.jsonc"
        
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("invalid json content {")
        
        with self.assertRaises(ValueError) as context:
            get_vendor_path_from_wrangler_config(self.project_path)
        
        self.assertIn("Could not process", str(context.exception))

    def test_missing_main_field(self):
        """Test error when main field is missing."""
        # Create test wrangler.toml without main field
        config_path = self.project_path / "wrangler.toml"
        
        with open(config_path, "w", encoding="utf-8") as f:
            # Create TOML without main field
            f.write('name = "my-worker"\n')
        
        with self.assertRaises(ValueError) as context:
            get_vendor_path_from_wrangler_config(self.project_path)
        
        self.assertIn("'main' field not found", str(context.exception))

    def test_main_field_not_string(self):
        """Test error when main field is not a string."""
        # Create test wrangler.toml with non-string main field
        config_path = self.project_path / "wrangler.toml"
        
        with open(config_path, "w", encoding="utf-8") as f:
            # Create TOML with non-string main
            f.write('main = 123\n')
        
        with self.assertRaises(ValueError) as context:
            get_vendor_path_from_wrangler_config(self.project_path)
        
        self.assertIn("must be a string", str(context.exception))

    def test_empty_main_field(self):
        """Test error when main field is empty."""
        # Create test wrangler.toml with empty main field
        config_content = {"main": ""}
        config_path = self.project_path / "wrangler.toml"
        
        with open(config_path, "w", encoding="utf-8") as f:
            # Create valid TOML format manually since we can't depend on a TOML writer
            f.write(f'main = "{config_content["main"]}"\n')
        
        with self.assertRaises(ValueError) as context:
            get_vendor_path_from_wrangler_config(self.project_path)
        
        self.assertIn("cannot be empty", str(context.exception))

    def test_both_config_files_raises_error(self):
        """Test that an error is raised when both wrangler.toml and wrangler.jsonc exist."""
        # Create both config files with different main fields
        toml_config = {"main": "src/worker.js"}
        toml_path = self.project_path / "wrangler.toml"
        
        with open(toml_path, "w", encoding="utf-8") as f:
            # Create valid TOML format manually
            f.write(f'main = "{toml_config["main"]}"\n')
            
        jsonc_config = {"main": "dist/index.js"}
        jsonc_path = self.project_path / "wrangler.jsonc"
        
        with open(jsonc_path, "w", encoding="utf-8") as f:
            json.dump(jsonc_config, f)
        
        # The function should raise a ValueError when both files exist
        with self.assertRaises(ValueError) as context:
            get_vendor_path_from_wrangler_config(self.project_path)
            
        # Check that the error message mentions the ambiguous configuration
        self.assertIn("Ambiguous configuration", str(context.exception))
        self.assertIn("both wrangler.toml and wrangler.jsonc exist", str(context.exception))
