"""Skill loader — loads SKILL.md files with progressive disclosure."""

import os
import yaml
from typing import Optional, TypedDict
from src.db.store import AegisStore


class SkillSpec(TypedDict, total=False):
    """Parsed skill specification."""
    name: str
    description: str
    compatibility: str
    body: str
    source: str


# In-memory skill cache
_loaded_skills: dict[str, SkillSpec] = {}


async def load_skill(skill_name: str, db_store: AegisStore = None) -> Optional[SkillSpec]:
    """Load SKILL.md, parse frontmatter, return spec.

    Progressive disclosure:
    1. Check in-memory cache (fastest)
    2. Load from skills/ directory
    3. Load from .agents/skills/cache/ (downloaded skills)

    Args:
        skill_name: Name of skill to load

    Returns:
        Parsed SkillSpec or None if not found
    """
    # Check cache first
    if skill_name in _loaded_skills:
        return _loaded_skills[skill_name]

    # Try built-in skills directory
    skill_paths = [
        f"skills/{skill_name}/SKILL.md",
        f"skills/{skill_name}.md",
        f".agents/skills/cache/{skill_name}/SKILL.md",
    ]

    for path in skill_paths:
        if not os.path.exists(path):
            continue

        with open(path, "r") as f:
            content = f.read()

        # Parse YAML frontmatter
        spec = _parse_skill_md(content)
        spec["source"] = path
        _loaded_skills[skill_name] = spec

        # Update DB if provided
        if db_store:
            await db_store.add_skill(
                name=skill_name,
                source="built-in" if path.startswith("skills/") else "cached",
                description=spec.get("description", ""),
            )

        print(f"Loaded skill: {skill_name}")
        return spec

    return None


async def unload_skill(skill_name: str) -> None:
    """Remove skill from active context."""
    if skill_name in _loaded_skills:
        del _loaded_skills[skill_name]
        print(f"Unloaded skill: {skill_name}")


def get_active_skills() -> list[str]:
    """Return list of currently loaded skills."""
    return list(_loaded_skills.keys())


def _parse_skill_md(content: str) -> SkillSpec:
    """Parse SKILL.md with YAML frontmatter.

    Format:
    ---
    name: skill-name
    description: Short description
    compatibility: Python 3.12+
    ---

    # Skill Body
    ...
    """
    if not content.startswith("---"):
        return SkillSpec(name="unknown", body=content)

    parts = content.split("---", 2)
    if len(parts) < 3:
        return SkillSpec(name="unknown", body=content)

    # Parse frontmatter
    frontmatter = yaml.safe_load(parts[1])
    body = parts[2].strip()

    return SkillSpec(
        name=frontmatter.get("name", "unknown"),
        description=frontmatter.get("description", ""),
        compatibility=frontmatter.get("compatibility", ""),
        body=body,
    )


async def main():
    """Test mode: load built-in skills."""
    skills_dir = "skills"
    if not os.path.exists(skills_dir):
        print(f"Skills directory not found: {skills_dir}")
        return

    builtin_skills = [
        "bidding-strategy",
        "research",
        "code-delivery",
        "validation",
        "wallet-management",
    ]

    for skill_name in builtin_skills:
        spec = await load_skill(skill_name)
        if spec:
            print(f"✓ {skill_name}: {spec.get('description', 'N/A')[:50]}")
        else:
            print(f"✗ {skill_name}: NOT FOUND")

    print(f"\nActive skills: {get_active_skills()}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
