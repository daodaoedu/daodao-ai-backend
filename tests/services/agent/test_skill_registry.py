"""
Skill registry tests: 載入、metadata、漸進式載入 (tasks 11.3).
"""

from pathlib import Path

from src.services.agent.agent import _SKILLS_DIR, SkillLoader


def _make_skill(tmp_path: Path, name: str, description: str, body: str = "steps") -> Path:
    skill_dir = tmp_path / name
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return skill_md


class TestSkillLoader:

    def test_loads_metadata_from_frontmatter(self, tmp_path):
        _make_skill(tmp_path, "monthly-report", "產出月報")
        skills = SkillLoader().load_skills(tmp_path)

        assert len(skills) == 1
        assert skills[0]["name"] == "monthly-report"
        assert skills[0]["description"] == "產出月報"

    def test_merges_multiple_skills_into_registry(self, tmp_path):
        _make_skill(tmp_path, "skill-a", "A")
        _make_skill(tmp_path, "skill-b", "B")
        skills = SkillLoader().load_skills(tmp_path)
        assert {s["name"] for s in skills} == {"skill-a", "skill-b"}

    def test_progressive_loading_metadata_only(self, tmp_path):
        # 啟動時只載 metadata，不含完整內容（漸進式載入）
        _make_skill(tmp_path, "big-skill", "big", body="FULL CONTENT " * 100)
        skills = SkillLoader().load_skills(tmp_path)
        assert "FULL CONTENT" not in str(skills)

        # 觸發時才讀完整內容
        content = SkillLoader().get_skill_content(Path(skills[0]["path"]))
        assert "FULL CONTENT" in content

    def test_skips_malformed_frontmatter(self, tmp_path):
        skill_dir = tmp_path / "broken"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("no frontmatter here", encoding="utf-8")
        assert SkillLoader().load_skills(tmp_path) == []

    def test_missing_dir_returns_empty(self, tmp_path):
        assert SkillLoader().load_skills(tmp_path / "nope") == []

    def test_static_skills_shipped_in_repo_are_loadable(self):
        # repo 內建的兩個 Static Skill 應可載入
        skills = SkillLoader().load_skills(_SKILLS_DIR)
        names = {s["name"] for s in skills}
        assert "practice_completion_email" in names
        assert "monthly_insights" in names
