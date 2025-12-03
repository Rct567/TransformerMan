"""
Tests for LM client.
"""

from __future__ import annotations


from transformerman.lib.lm_client import DummyLMClient


def test_dummy_client_basic_response():
    """Test that DummyLMClient returns valid XML response."""
    client = DummyLMClient()

    prompt = '''<notes model="Basic">
  <note nid="123" deck="Test Deck">
    <field name="Front">Hello</field>
    <field name="Back"></field>
  </note>
</notes>'''

    response = client.transform(prompt)

    assert '<notes model="Basic">' in response
    assert 'nid="123"' in response
    assert '<field name="Front">Hello</field>' in response
    assert '<field name="Back">Mock content for Back</field>' in response


def test_dummy_client_multiple_notes():
    """Test DummyLMClient with multiple notes."""
    client = DummyLMClient()

    prompt = '''<notes model="Basic">
  <note nid="123" deck="Test">
    <field name="Front">Q1</field>
    <field name="Back"></field>
  </note>
  <note nid="456" deck="Test">
    <field name="Front">Q2</field>
    <field name="Back"></field>
  </note>
</notes>'''

    response = client.transform(prompt)

    assert 'nid="123"' in response
    assert 'nid="456"' in response
    assert response.count('Mock content for Back') == 2


def test_dummy_client_preserves_existing_content():
    """Test that DummyLMClient preserves existing field content."""
    client = DummyLMClient()

    prompt = '''<notes model="Basic">
  <note nid="123" deck="Test">
    <field name="Front">Existing Front</field>
    <field name="Back">Existing Back</field>
  </note>
</notes>'''

    response = client.transform(prompt)

    assert '<field name="Front">Existing Front</field>' in response
    assert '<field name="Back">Existing Back</field>' in response
    assert 'Mock content' not in response


def test_dummy_client_empty_prompt():
    """Test DummyLMClient with empty prompt."""
    client = DummyLMClient()

    response = client.transform("")

    assert response == '<notes></notes>'
