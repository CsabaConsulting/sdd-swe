"""Skill catalog scanner — finds built-in and cached skills."""

import os
import asyncio
from typing import TypedDict


class SkillMatch(TypedDict):
    """Result from catalog search."""
    name: str
    description: str
    source: str
    relevance_score: float
    last_updated: str


# Default configured catalogs
CATALOGS = [
    "github/heilcheng/awesome-agent-skills",
    "github/CommandCodeAI/agent-skills",
    "github/MoizIbnYousaf/Ai-Agent-Skills",
    "github/github/awesome-copilot/skills",
]


async def scan_builtin_skills() -> list[dict]:
    """Scan skills/ directory for built-in SKILL.md files.

    Returns:
        List of skill specs with name, description, source
    """
    skills_dir = "skills"
    if not os.path.exists(skills_dir):
        return []

    skills = []
    for entry in os.listdir(skills_dir):
        skill_path = os.path.join(skills_dir, entry)
        if not os.path.isdir(skill_path):
            continue

        md_path = os.path.join(skill_path, "SKILL.md")
        if not os.path.exists(md_path):
            continue

        # Parse minimal frontmatter
        with open(md_path, "r") as f:
            content = f.read()

        name = entry
        description = ""
        if "---" in content:
            parts = content.split("---", 2)
            if len(parts) >= 2:
                import yaml
                frontmatter = yaml.safe_load(parts[1])
                name = frontmatter.get("name", entry)
                description = frontmatter.get("description", "")

        skills.append({
            "name": name,
            "description": description,
            "source": "built-in",
        })

    return skills


async def scan_cached_skills() -> list[dict]:
    """Scan .agents/skills/cache/ for downloaded skills.

    Returns:
        List of cached skill specs
    """
    cache_dir = ".agents/skills/cache"
    if not os.path.exists(cache_dir):
        return []

    skills = []
    for entry in os.listdir(cache_dir):
        skill_path = os.path.join(cache_dir, entry, "SKILL.md")
        if os.path.exists(skill_path):
            skills.append({
                "name": entry,
                "description": "Cached skill",
                "source": f"cache/{entry}",
            })

    return skills


async def search_catalogs(keywords: str) -> list[SkillMatch]:
    """Search configured catalogs for matching skills.

    Note: This is a stub — real implementation would query each catalog's
    API endpoint. For the hackathon, we return cached results.

    Args:
        keywords: Search keywords

    Returns:
        Ranked list of skill matches
    """
    # Stub: return empty list
    # Real implementation:
    # 1. Query each catalog's search endpoint
    # 2. Parse results
    # 3. Rank by: relevance, reputation, recency
    # 4. Return top matches
    return []


async def download_skill(skill_url: str) -> dict:
    """Download SKILL.md from catalog, verify checksum.

    Args:
        skill_url: URL to skill in catalog

    Returns:
        SkillSpec with downloaded content

    Raises:
        ValueError: If checksum verification fails
    """
    # Stub: would download from URL
    # Real implementation:
    # 1. Download SKILL.md + checksum from catalog
    # 2. Verify checksum matches
    # 3. Return spec for vetting
    raise NotImplementedError("download_skill not implemented")


async def main():
    """Test mode: scan built-in skills."""
    builtin = await scan_builtin_skills()
    print(f"Built-in skills ({len(builtin)}):")
    for skill in builtin:
        print(f"  ✓ {skill['name']}: {skill['description'][:50] or 'N/A'}")

    cached = await scan_cached_skills()
    print(f"\nCached skills ({len(cached)}):")
    for skill in cached:
        print(f"  ✓ {skill['name']}: {skill['source']}")

    results = await search_catalogs("python")
    print(f"\nCatalog search results: {len(results)}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
