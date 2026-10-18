"""The skills people can tick on their profile. Slugs are stored; labels are for display.

Kept in code, not the database, so the list is easy to review and change. Connect Teams
will match on these slugs, so do not rename a slug once people have chosen it.
"""

from __future__ import annotations

SKILL_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Software and data",
        [
            ("web-dev", "Web development"),
            ("mobile-dev", "Mobile apps"),
            ("backend-apis", "Backend and APIs"),
            ("data-analytics", "Data and analytics"),
            ("ai-ml", "AI and machine learning"),
            ("automation", "Automation and RPA"),
            ("devops-security", "DevOps and security"),
            ("electronics", "Electronics and embedded"),
        ],
    ),
    (
        "Design and media",
        [
            ("ui-ux", "UI and UX design"),
            ("branding", "Graphic design and branding"),
            ("product-design", "Product and industrial design"),
            ("3d-modelling", "3D modelling and printing"),
            ("video-photo", "Video and photography"),
        ],
    ),
    (
        "Business",
        [
            ("product-mgmt", "Product management"),
            ("marketing-seo", "Marketing and SEO"),
            ("sales-partners", "Sales and partnerships"),
            ("finance", "Finance and fundraising"),
            ("legal", "Legal and compliance"),
            ("operations", "Operations and logistics"),
        ],
    ),
    (
        "Making and testing",
        [
            ("prototyping", "Prototyping and fabrication"),
            ("sourcing", "Sourcing and supply chain"),
            ("testing-qa", "Testing and QA"),
        ],
    ),
    (
        "Knowledge and people",
        [
            ("research-writing", "Research and writing"),
            ("teaching", "Teaching and coaching"),
            ("domain-expert", "Subject expert (health, education, trades...)"),
            ("community", "Community and moderation"),
            ("translation", "Translation and languages"),
        ],
    ),
]

SKILL_LABELS: dict[str, str] = {slug: label for _, items in SKILL_GROUPS for slug, label in items}

GOALS: dict[str, str] = {
    "share": "Share my own ideas",
    "join": "Join a team and help build",
    "offer": "Offer my skills to people who need them",
}


def clean_skills(values: list[str]) -> list[str]:
    """Keep only known skills, once each, in catalogue order."""
    wanted = set(values)
    return [slug for slug in SKILL_LABELS if slug in wanted]


def clean_goals(values: list[str]) -> list[str]:
    wanted = set(values)
    return [slug for slug in GOALS if slug in wanted]
