"""024 契约测试：creative-assets 技能、init 分发、移交包 WORKDIR.md 与文档指针。"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
TPL = ROOT / "resources" / "skills" / "creative-assets" / "SKILL.md"
COPY = ROOT / "skills" / "creative-assets" / "SKILL.md"
WORKDIR_TPL = ROOT / "resources" / "skills" / "creative-assets" / "WORKDIR.md"


def test_skill_template_exists_and_matches_copy():
    assert TPL.is_file() and COPY.is_file()
    assert TPL.read_bytes() == COPY.read_bytes()


def test_skill_frontmatter_and_six_sections():
    text = TPL.read_text(encoding="utf-8")
    assert "name: creative-assets" in text
    assert "创作团队" in text and "工作目录" in text
    # 六节
    for header in ["## 1. 资产从哪来", "## 2. 资产怎么编号",
                   "## 3. 资产归属", "## 4. 物理布局",
                   "## 5. 改版与重拍", "## 6. 移交"]:
        assert header in text
    # 三条铁律与命名规则
    assert "稳定键" in text
    assert "全项目唯一" in text and "只引用不复制" in text
    assert "N{ord:04d}" in text
    assert "first_seen_node" in text
    # 触发边界
    assert "narrative-sim" in text


def test_workdir_template_matches_skill_sections():
    wt = WORKDIR_TPL.read_text(encoding="utf-8")
    st = TPL.read_text(encoding="utf-8")
    assert "三条铁律" in wt and "first_seen_node" in wt
    assert "N{ord:04d}" in wt
    # 同源关键片段一致
    assert "只引用不复制" in wt and "只引用不复制" in st
    assert "`node_id` 是稳定键" in wt and "`node_id` 是稳定键" in st


def test_init_copies_creative_skill(tmp_path):
    from orchestrator import init_app
    result = init_app.initialize(tmp_path)
    target = tmp_path / "skills" / "creative-assets" / "SKILL.md"
    assert target.is_file()
    assert target.read_bytes() == TPL.read_bytes()
    entry = next(i for i in result["files"]
                 if i["path"].endswith("skills/creative-assets/SKILL.md"))
    assert entry["status"] == "created"


def test_init_preserves_existing_creative_skill(tmp_path):
    from orchestrator import init_app
    init_app.initialize(tmp_path)
    target = tmp_path / "skills" / "creative-assets" / "SKILL.md"
    target.write_bytes(b"custom-creative-skill")
    result = init_app.initialize(tmp_path)
    assert target.read_bytes() == b"custom-creative-skill"
    entry = next(i for i in result["files"]
                 if i["path"].endswith("skills/creative-assets/SKILL.md"))
    assert entry["status"] == "existing"


def test_docs_have_pointer(tmp_path):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    manual = (ROOT / "mydocs" / "叙事仿真系统开发手册.md").read_text(encoding="utf-8")
    for doc in (readme, manual):
        assert "creative-assets" in doc
        assert "三条铁律" in doc
        assert "first_seen_node" in doc
