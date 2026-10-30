from typing import TypedDict, Optional


class ParsedJD(TypedDict):
    role_title: str
    seniority_level: str          # junior | mid | senior | lead
    required_skills: list[str]
    preferred_skills: list[str]
    responsibilities: list[str]
    reporting_structure: Optional[str]
    growth_path: Optional[str]
    success_criteria: Optional[str]
    compensation: Optional[str]


class CompletenessResult(TypedDict):
    score: int                    # 0–100
    findings: list[str]
    missing: list[str]


class SkillSpecificityResult(TypedDict):
    score: int
    findings: list[str]
    vague_skills: list[str]


class CognitiveLoadResult(TypedDict):
    score: int
    findings: list[str]
    word_count: int
    grade_level: float


class InclusionResult(TypedDict):
    score: int
    findings: list[str]
    flags: list[str]


class CompensationResult(TypedDict):
    score: int
    findings: list[str]
    band_present: bool


class RoleCoherenceResult(TypedDict):
    score: int
    findings: list[str]
    mismatches: list[str]


class DimensionResults(TypedDict):
    completeness: CompletenessResult
    skill_specificity: SkillSpecificityResult
    cognitive_load: CognitiveLoadResult
    inclusion_signals: InclusionResult
    compensation: CompensationResult
    role_coherence: RoleCoherenceResult


class SuggestedAddition(TypedDict):
    section: str
    suggestion: str
    impact: str


class DimensionBreakdown(TypedDict):
    dimension: str
    score: int
    narrative: str


class AdvisorReport(TypedDict):
    jdqi_score: int
    benchmark_comparison: str
    dimension_breakdown: list[DimensionBreakdown]
    suggested_additions: list[SuggestedAddition]


class JDQIContext(TypedDict, total=False):
    jd_text: str
    industry: str
    parsed_jd: ParsedJD
    dimension_results: DimensionResults
    advisor_report: AdvisorReport


class RequiredSkill(TypedDict):
    name: str
    version_or_level: str


class SkippedDimension(TypedDict):
    dimension: str
    jdqi_impact_note: str


class JDQIBrief(TypedDict, total=False):
    role_title: str
    industry: str
    seniority_level: str          # junior | mid | senior | lead | director
    location: str
    remote_policy: str            # on-site | hybrid | remote | flexible
    company_description: str
    responsibilities: list[str]
    required_skills: list[RequiredSkill]
    preferred_skills: list[str]
    success_criteria: list[str]
    reporting_structure: Optional[str]
    growth_path: Optional[str]
    compensation: Optional[str]
    inclusion_statement: Optional[str]
    skipped_dimensions: list[SkippedDimension]


class JDDocument(TypedDict, total=False):
    role_title: str
    about_company: str
    about_role: str
    responsibilities: list[str]
    required_skills: list[str]
    preferred_skills: list[str]
    success_criteria: list[str]
    reporting_structure: Optional[str]
    growth_path: Optional[str]
    compensation: Optional[str]
    equal_opportunity: str
