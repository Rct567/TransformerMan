"""
Tests for XML parser.
"""

from __future__ import annotations

from anki.notes import NoteId

from transformerman.lib.xml_parser import new_notes_from_xml, notes_from_xml, escape_xml_content, unescape_xml_content, NewNote
from transformerman.lib.field_updates import FieldUpdates


class TestXmlParser:
    """Test class for XML parser."""

    def test_notes_from_xml_multiple_notes(self) -> None:
        """Test parsing multiple notes."""
        xml = """<notes model="Basic">
        <note nid="123" deck="Test">
            <field name="Front">Q1</field>
            <field name="Back">A1</field>
        </note>
        <note nid="456" deck="Test">
            <field name="Front">Q2</field>
            <field name="Back">A2</field>
        </note>
        </notes>"""

        result = notes_from_xml(xml)

        assert len(result) == 2
        assert result[NoteId(123)]["Front"] == "Q1"
        assert result[NoteId(456)]["Back"] == "A2"

    def test_notes_from_xml_with_escaped_content(self) -> None:
        """Test parsing XML response with escaped content."""
        # Use escape_xml_content to generate the escaped XML
        # This ensures we're testing with the same escaping that would be used in production
        front_content = "x < y & z > 0"
        back_content = '"Hello" & \'World\''

        escaped_front = escape_xml_content(front_content)
        escaped_back = escape_xml_content(back_content)

        xml = f"""<notes model="Basic">
        <note nid="123" deck="Test">
            <field name="Front">{escaped_front}</field>
            <field name="Back">{escaped_back}</field>
        </note>
        </notes>"""

        result = notes_from_xml(xml)

        assert NoteId(123) in result
        assert result[NoteId(123)]["Front"] == front_content
        assert result[NoteId(123)]["Back"] == back_content

    def test_notes_from_xml_empty_response(self) -> None:
        """Test parsing empty XML response."""
        xml = "<notes></notes>"

        result = notes_from_xml(xml)

        assert len(result) == 0
        assert isinstance(result, FieldUpdates)

    def test_notes_from_xml_malformed_xml(self) -> None:
        """Test parsing malformed XML raises ValueError."""
        xml = '<notes><note nid="123">'  # Unclosed tags

        # Should still work with regex-based parsing
        result = notes_from_xml(xml)
        assert len(result) == 0
        assert isinstance(result, FieldUpdates)

    def test_escape_xml_content(self) -> None:
        """Test XML content escaping."""
        content = '<tag>Hello & "World"</tag>'
        escaped = escape_xml_content(content)

        assert escaped == "&lt;tag&gt;Hello &amp; &quot;World&quot;&lt;/tag&gt;"

    def test_unescape_xml_content(self) -> None:
        """Test XML content unescaping."""
        content = "&lt;tag&gt;Hello &amp; &quot;World&quot;&lt;/tag&gt;"
        unescaped = unescape_xml_content(content)

        assert unescaped == '<tag>Hello & "World"</tag>'

    def test_escape_unescape_roundtrip(self) -> None:
        """Test that escape and unescape are inverses."""
        original = '<div>Test & "quotes" with \'apostrophes\'</div>'
        escaped = escape_xml_content(original)
        unescaped = unescape_xml_content(escaped)

        assert unescaped == original

    def test_new_notes_from_xml_root_deck(self) -> None:
        xml = """
        <notes model="Basic" deck="Default">
        <note>
            <field name="Front">Front 1</field>
            <field name="Back">Back 1</field>
        </note>
        <note>
            <field name="Front">Front 2</field>
            <field name="Back">Back 2</field>
        </note>
        </notes>
        """
        notes = new_notes_from_xml(xml)
        assert len(notes) == 2
        assert notes[0]["Front"] == "Front 1"
        assert notes[0].deck_name == "Default"
        assert notes[0].model_name == "Basic"
        assert notes[1]["Back"] == "Back 2"
        assert notes[1].deck_name == "Default"
        assert notes[1].model_name == "Basic"

    def test_new_notes_from_xml_mixed_decks(self) -> None:
        xml = """
        <notes model="Basic">
        <note deck="Deck A">
            <field name="Front">Front A</field>
        </note>
        <note deck="Deck B">
            <field name="Front">Front B</field>
        </note>
        </notes>
        """
        notes = new_notes_from_xml(xml)
        assert len(notes) == 2
        assert notes[0].deck_name == "Deck A"
        assert notes[1].deck_name == "Deck B"

    def test_new_notes_from_xml_mixed_models(self) -> None:
        xml = """
        <notes model="RootModel">
        <note model="NoteModel A">
            <field name="Front">Front A</field>
        </note>
        <note>
            <field name="Front">Front B</field>
        </note>
        </notes>
        """
        notes = new_notes_from_xml(xml)
        assert len(notes) == 2
        assert notes[0].model_name == "NoteModel A"
        assert notes[1].model_name == "RootModel"

    def test_new_notes_from_xml_unescape(self) -> None:
        xml = """
        <notes model="Basic">
        <note>
            <field name="Front">A &amp; B &lt; C</field>
        </note>
        </notes>
        """
        notes = new_notes_from_xml(xml)
        assert notes[0]["Front"] == "A & B < C"

    def test_new_note_class_behavior(self) -> None:
        """Test that NewNote acts like a dict for fields but has attributes for metadata."""
        fields = {"Front": "Q", "Back": "A"}
        note = NewNote(fields, deck_name="MyDeck", model_name="MyModel")

        # Dict-like access
        assert note["Front"] == "Q"
        assert note.get("Back") == "A"
        assert "Front" in note
        assert list(note.keys()) == ["Front", "Back"]
        assert list(note.values()) == ["Q", "A"]
        assert list(note.items()) == [("Front", "Q"), ("Back", "A")]

        # Metadata attributes
        assert note.deck_name == "MyDeck"
        assert note.model_name == "MyModel"

        # Modification
        note["Front"] = "New Q"
        assert note["Front"] == "New Q"
        assert fields["Front"] == "New Q"  # Should modify the underlying dict

    def test_notes_from_xml_unescaped_html(self) -> None:
        """Test parsing XML response with unescaped HTML content."""
        xml = """<notes>
        <note nid="123">
            <field name="Front"><b>Bold</b> and <i>Italic</i></field>
            <field name="Back">1 < 2</field>
        </note>
        </notes>"""

        result = notes_from_xml(xml)

        assert NoteId(123) in result
        assert result[NoteId(123)]["Front"] == "<b>Bold</b> and <i>Italic</i>"
        assert result[NoteId(123)]["Back"] == "1 < 2"

    def test_new_notes_from_xml_unescaped_html(self) -> None:
        """Test parsing new notes XML response with unescaped HTML content."""
        xml = """<notes model="Basic">
        <note>
            <field name="Front"><b>Bold</b> and <i>Italic</i></field>
            <field name="Back">1 < 2</field>
        </note>
        </notes>"""

        notes = new_notes_from_xml(xml)

        assert len(notes) == 1
        assert notes[0]["Front"] == "<b>Bold</b> and <i>Italic</i>"
        assert notes[0]["Back"] == "1 < 2"
