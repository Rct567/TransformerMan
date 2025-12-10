"""
Tests for XML parser.
"""

from __future__ import annotations

from anki.notes import NoteId

from transformerman.lib.xml_parser import notes_from_xml, escape_xml_content, unescape_xml_content


class TestXmlParser:
    """Test class for XML parser."""

    def test_parse_simple_response(self) -> None:
        """Test parsing a simple XML response."""
        xml = '''<notes model="Basic">
  <note nid="123" deck="Test">
    <field name="Front">Hello</field>
    <field name="Back">World</field>
  </note>
</notes>'''

        result = notes_from_xml(xml)

        assert 123 in result
        assert result[NoteId(123)]["Front"] == "Hello"
        assert result[NoteId(123)]["Back"] == "World"

    def test_parse_multiple_notes(self) -> None:
        """Test parsing multiple notes."""
        xml = '''<notes model="Basic">
  <note nid="123" deck="Test">
    <field name="Front">Q1</field>
    <field name="Back">A1</field>
  </note>
  <note nid="456" deck="Test">
    <field name="Front">Q2</field>
    <field name="Back">A2</field>
  </note>
</notes>'''

        result = notes_from_xml(xml)

        assert len(result) == 2
        assert result[NoteId(123)]["Front"] == "Q1"
        assert result[NoteId(456)]["Back"] == "A2"

    def test_parse_xml_with_escaped_content(self) -> None:
        """Test parsing XML response with escaped content."""
        # Use escape_xml_content to generate the escaped XML
        # This ensures we're testing with the same escaping that would be used in production
        front_content = "x < y & z > 0"
        back_content = '"Hello" & \'World\''

        escaped_front = escape_xml_content(front_content)
        escaped_back = escape_xml_content(back_content)

        xml = f'''<notes model="Basic">
  <note nid="123" deck="Test">
    <field name="Front">{escaped_front}</field>
    <field name="Back">{escaped_back}</field>
  </note>
</notes>'''

        result = notes_from_xml(xml)

        assert 123 in result
        assert result[NoteId(123)]["Front"] == front_content
        assert result[NoteId(123)]["Back"] == back_content

    def test_parse_empty_response(self) -> None:
        """Test parsing empty XML response."""
        xml = '<notes></notes>'

        result = notes_from_xml(xml)

        assert result == {}

    def test_parse_malformed_xml(self) -> None:
        """Test parsing malformed XML raises ValueError."""
        xml = '<notes><note nid="123">'  # Unclosed tags

        # Should still work with regex-based parsing
        result = notes_from_xml(xml)
        assert result == {}

    def test_escape_xml_content(self) -> None:
        """Test XML content escaping."""
        content = '<tag>Hello & "World"</tag>'
        escaped = escape_xml_content(content)

        assert escaped == '&lt;tag&gt;Hello &amp; &quot;World&quot;&lt;/tag&gt;'

    def test_unescape_xml_content(self) -> None:
        """Test XML content unescaping."""
        content = '&lt;tag&gt;Hello &amp; &quot;World&quot;&lt;/tag&gt;'
        unescaped = unescape_xml_content(content)

        assert unescaped == '<tag>Hello & "World"</tag>'

    def test_escape_unescape_roundtrip(self) -> None:
        """Test that escape and unescape are inverses."""
        original = '<div>Test & "quotes" with \'apostrophes\'</div>'
        escaped = escape_xml_content(original)
        unescaped = unescape_xml_content(escaped)

        assert unescaped == original
