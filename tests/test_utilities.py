"""Tests for utilities module."""

from __future__ import annotations

from transformerman.lib.utilities import create_slug


class TestUtilities:
    """Test class for create_slug function."""

    def test_basic_conversion(self) -> None:
        """Test basic string to slug conversion."""
        assert create_slug("My Field Name") == "my_field_name"
        assert create_slug("Front") == "front"
        assert create_slug("Back Extra") == "back_extra"

    def test_special_characters(self) -> None:
        """Test that special characters are replaced with underscores."""
        assert create_slug("Field Name!") == "field_name"
        assert create_slug("Field@Name#") == "field_name"
        assert create_slug("Field-Name") == "field_name"
        assert create_slug("Field.Name") == "field_name"

    def test_multiple_spaces(self) -> None:
        """Test that multiple spaces are collapsed to single underscore."""
        assert create_slug("Field  With   Spaces") == "field_with_spaces"
        assert create_slug("Field    Name") == "field_name"

    def test_leading_trailing_special_chars(self) -> None:
        """Test that leading/trailing special characters are removed."""
        assert create_slug("_Field_") == "field"
        assert create_slug("__Field__") == "field"
        assert create_slug("!Field!") == "field"

    def test_consecutive_special_chars(self) -> None:
        """Test that consecutive special characters are collapsed."""
        assert create_slug("Field!!!Name") == "field_name"
        assert create_slug("Field---Name") == "field_name"

    def test_numbers_preserved(self) -> None:
        """Test that numbers are preserved in slugs."""
        assert create_slug("Field 1") == "field_1"
        assert create_slug("Field123") == "field123"
        assert create_slug("Field 1 Name 2") == "field_1_name_2"

    def test_empty_and_edge_cases(self) -> None:
        """Test edge cases."""
        assert create_slug("") == ""
        assert create_slug("!!!") == ""
        assert create_slug("   ") == ""
        assert create_slug("a") == "a"
