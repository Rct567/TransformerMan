"""
Tests for XML parser.
"""

from __future__ import annotations

from transformerman.lib.xml_parser import notes_from_xml, escape_xml_content, unescape_xml_content


def test_parse_simple_response():
    """Test parsing a simple XML response."""
    xml = '''<notes model="Basic">
  <note nid="123" deck="Test">
    <field name="Front">Hello</field>
    <field name="Back">World</field>
  </note>
</notes>'''

    result = notes_from_xml(xml)

    assert 123 in result
    assert result[123]["Front"] == "Hello"
    assert result[123]["Back"] == "World"


def test_parse_multiple_notes():
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
    assert result[123]["Front"] == "Q1"
    assert result[456]["Back"] == "A2"


def test_parse_empty_response():
    """Test parsing empty XML response."""
    xml = '<notes></notes>'

    result = notes_from_xml(xml)

    assert result == {}


def test_parse_malformed_xml():
    """Test parsing malformed XML raises ValueError."""
    xml = '<notes><note nid="123">'  # Unclosed tags

    # Should still work with regex-based parsing
    result = notes_from_xml(xml)
    assert result == {}


def test_escape_xml_content():
    """Test XML content escaping."""
    content = '<tag>Hello & "World"</tag>'
    escaped = escape_xml_content(content)

    assert escaped == '&lt;tag&gt;Hello &amp; &quot;World&quot;&lt;/tag&gt;'


def test_unescape_xml_content():
    """Test XML content unescaping."""
    content = '&lt;tag&gt;Hello &amp; &quot;World&quot;&lt;/tag&gt;'
    unescaped = unescape_xml_content(content)

    assert unescaped == '<tag>Hello & "World"</tag>'


def test_escape_unescape_roundtrip():
    """Test that escape and unescape are inverses."""
    original = '<div>Test & "quotes" with \'apostrophes\'</div>'
    escaped = escape_xml_content(original)
    unescaped = unescape_xml_content(escaped)

    assert unescaped == original
