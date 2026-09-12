"""
Tests for glossary module (PLAN-034d0：键规范化)
"""
import csv
from io import StringIO

import pytest

from qyunslation.glossary.glossary import Glossary


def test_glossary_initialization():
    """Test Glossary initialization"""
    glossary = Glossary()
    assert glossary.glossary_dict == {}

    # With initial dict — keys normalized (casefold)
    initial_dict = {"Hello": "你好", "World": "世界"}
    glossary = Glossary(initial_dict)
    assert glossary.glossary_dict == {"hello": "你好", "world": "世界"}


def test_glossary_update():
    """Test Glossary update method"""
    glossary = Glossary()

    glossary.update({"hello": "你好"})
    assert glossary.glossary_dict == {"hello": "你好"}

    glossary.update({"HELLO": "您好"})
    assert glossary.glossary_dict.get("hello") == "你好"  # Should not overwrite

    glossary.update({"world": "世界"})
    assert glossary.glossary_dict == {"hello": "你好", "world": "世界"}

    glossary.update({"  test  ": "测试"})
    assert "test" in glossary.glossary_dict
    assert glossary.glossary_dict["test"] == "测试"


def test_append_system_prompt():
    """Test Glossary append_system_prompt method"""
    glossary = Glossary({"hello": "你好", "world": "世界"})

    prompt = glossary.append_system_prompt("Hello there!")
    assert "必须使用指定译法" in prompt
    assert "hello => 你好" in prompt
    assert "world => 世界" not in prompt

    prompt = glossary.append_system_prompt("Hello world!")
    assert "hello => 你好" in prompt
    assert "world => 世界" in prompt

    prompt = glossary.append_system_prompt("This is a test")
    assert prompt == ""


def test_append_system_prompt_case_insensitive():
    """Test append_system_prompt is case insensitive"""
    glossary = Glossary({"Hello": "你好"})

    prompt = glossary.append_system_prompt("hello there")
    assert "hello => 你好" in prompt

    prompt = glossary.append_system_prompt("HELLO there")
    assert "hello => 你好" in prompt


def test_glossary_dict2csv():
    """Test glossary_dict2csv static method"""
    glossary_dict = {"hello": "你好", "world": "世界"}
    doc = Glossary.glossary_dict2csv(glossary_dict)

    assert doc.suffix == ".csv"
    assert doc.stem == "glossary_gen"

    content = doc.content.decode("utf-8")
    assert content.startswith("\ufeff")
    assert "src,dst" in content
    assert "hello,你好" in content
    assert "world,世界" in content

    content_without_bom = content[1:] if content.startswith("\ufeff") else content
    reader = csv.reader(StringIO(content_without_bom))
    rows = list(reader)
    assert rows[0] == ["src", "dst"]
    assert len(rows) == 3


def test_glossary_dict2csv_custom_delimiter():
    """Test glossary_dict2csv with custom delimiter"""
    glossary_dict = {"hello": "你好"}
    doc = Glossary.glossary_dict2csv(glossary_dict, delimiter="\t", stem="custom")

    assert doc.stem == "custom"
    content = doc.content.decode("utf-8")
    assert "src\tdst" in content
