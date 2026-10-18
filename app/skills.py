"""The skills people can tick on their profile. Slugs are stored; labels are for display.

Kept in code, not the database, so the list is easy to review and change. Connect Teams
will match on these slugs, so do not rename a slug once people have chosen it.
"""

from __future__ import annotations

def _slug(label: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in label)
    return "-".join(part for part in out.split("-") if part)[:50]


# Existing slugs are kept exactly. New entries are plain labels and get a slug from the label.
_RAW: list[tuple[str, list[str | tuple[str, str]]]] = [
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
            "Software developer", "Frontend developer", "Full-stack developer", "HTML and CSS",
            "JavaScript and TypeScript", "React", "Python", "Java", "C# and .NET", "Go", "Rust",
            "PHP", "Ruby", "SQL and databases", "Data engineering", "Data science",
            "Machine learning engineer", "Prompt engineering", "Cloud engineering (AWS, Azure, GCP)",
            "Cybersecurity", "Site reliability", "Game development", "Blockchain", "Low-code and no-code",
            "Excel and spreadsheets", "Power BI and Tableau", "Business analysis", "Systems administration",
            "Networking", "API integration", "Web scraping", "Technical writing", "Software architecture",
            "UiPath", "Power Automate", "Robotics", "Internet of things", "Embedded C and C++",
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
            "Illustration", "Animation and motion graphics", "Video editing", "Photography",
            "Audio and music production", "Sound design", "Copywriting", "Content creation",
            "Social media", "Figma", "Architecture and interiors", "Fashion and textiles",
            "Game art", "CAD", "Packaging design", "Presentation design",
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
            "Project management", "Agile and Scrum", "Business development", "Entrepreneurship",
            "Strategy and consulting", "Accounting and bookkeeping", "Financial modelling",
            "Investor relations", "Grant writing", "Customer support", "Customer research",
            "Market research", "Pricing", "Brand strategy", "Email marketing", "Paid advertising",
            "Public relations", "E-commerce", "Human resources", "Recruiting", "Intellectual property",
            "Contracts", "Privacy and data protection", "Procurement", "Event management",
        ],
    ),
    (
        "Making and testing",
        [
            ("prototyping", "Prototyping and fabrication"),
            ("sourcing", "Sourcing and supply chain"),
            ("testing-qa", "Testing and QA"),
            "Mechanical engineering", "Electrical engineering", "Civil engineering", "Chemical engineering",
            "Manufacturing", "3D printing", "CNC and machining", "Welding and metalwork",
            "Woodworking", "Electronics repair", "PCB design", "Quality assurance", "Test automation",
            "User testing", "Materials science", "Sustainability and energy", "Construction",
            "Agriculture and farming", "Food production",
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
            "Scientific research", "Academic writing", "Journalism", "Editing and proofreading",
            "Mentoring", "Public speaking", "Facilitation", "Community management", "Nonprofit and charity",
            "Healthcare", "Nursing", "Mental health support", "Education and curriculum",
            "Early childhood", "Social work", "Accessibility", "Psychology", "Economics", "Statistics",
            "Mathematics", "Physics", "Biology", "Chemistry", "Environmental science", "Law",
            "Government and policy", "Tourism and hospitality", "Sports and fitness", "Music", "Cooking",
        ],
    ),
]

SKILL_GROUPS: list[tuple[str, list[tuple[str, str]]]] = []
for _group, _items in _RAW:
    _seen: set[str] = set()
    _out: list[tuple[str, str]] = []
    for _item in _items:
        slug, label = _item if isinstance(_item, tuple) else (_slug(_item), _item)
        if slug not in _seen:
            _seen.add(slug)
            _out.append((slug, label))
    SKILL_GROUPS.append((_group, _out))

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


def clean_custom_skills(values: list[str], limit: int = 10) -> list[str]:
    """Normalise skills people typed themselves: trimmed, single spaces, 2-50 characters, once each.

    A custom skill that matches a catalogue label is dropped, because the catalogue entry is used instead.
    """
    known = {label.lower() for label in SKILL_LABELS.values()}
    out: list[str] = []
    for raw in values:
        text = " ".join(raw.replace("\n", " ").split())[:50].strip()
        key = text.lower()
        if len(text) < 2 or key in known or key in {o.lower() for o in out}:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def catalogue_json() -> list[dict[str, str]]:
    """Flat list for the search box on the profile form."""
    return [
        {"slug": slug, "label": label, "group": group}
        for group, items in SKILL_GROUPS
        for slug, label in items
    ]


def clean_goals(values: list[str]) -> list[str]:
    wanted = set(values)
    return [slug for slug in GOALS if slug in wanted]
