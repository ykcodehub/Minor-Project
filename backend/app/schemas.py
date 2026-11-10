from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Language = Literal["en", "hi", "hinglish"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Strict):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class EmailRequest(Strict):
    email: EmailStr


class TokenRequest(Strict):
    token: str = Field(min_length=32, max_length=100)
    password: str | None = Field(default=None, min_length=12, max_length=128)


class RegistrationComplete(TokenRequest):
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)


class LanguageInput(Strict):
    language: Language


class TextInput(Strict):
    name: str = Field(default="Pasted document.txt", min_length=1, max_length=240)
    text: str = Field(min_length=1, max_length=2_000_000)


class DiscoveryInput(Strict):
    url: str = Field(max_length=2048)


class URLInput(DiscoveryInput):
    discovery_job_id: str


class AnalysisInput(Strict):
    source_ids: list[str] = Field(min_length=1, max_length=10)
    provider: Literal["gemini", "groq", "openrouter"] | None = None
    consent: bool = False
    privacy_mode: Literal["external", "confidential"] = "confidential"
    fallback_providers: list[Literal["gemini", "groq", "openrouter"]] = Field(
        default_factory=list, max_length=2
    )


class RetryInput(Strict):
    acknowledge_uncertain_calls: bool = False


class QuestionInput(Strict):
    language: Language | None = None
    question: str = Field(min_length=1, max_length=4000)


class AccountInput(Strict):
    authorized_providers: list[Literal["gemini", "groq", "openrouter"]] | None = Field(
        default=None, max_length=3
    )
    language: Language | None = None
    retention_days: int = Field(ge=1, le=30)
    preferred_provider: Literal["gemini", "groq", "openrouter"]


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class SectionResponse(ResponseModel):
    id: str
    source_id: str
    ordinal: int
    text: str
    page: int | None = None
    heading: str = ""
    locator: dict = Field(default_factory=dict)


class SourceResponse(ResponseModel):
    id: str
    source_id: str
    original_name: str
    kind: str
    sha256: str
    captured_at: str
    expires_at: str
    source_url: str | None = None
    status: str
    version: str
    sections: list[SectionResponse] = Field(default_factory=list)


class CitationResponse(ResponseModel):
    source_id: str
    section_id: str
    quote: str
    start: int | None
    end: int | None
    page: int | None = None
    match_status: Literal["EXACT", "NORMALIZED", "OCR_ESTIMATED", "INVALID"]


class FindingResponse(ResponseModel):
    id: str
    finding_id: str
    category: str
    statement: str
    rationale: str = ""
    qualifications: list[str] = Field(default_factory=list)
    support_status: Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "AMBIGUOUS"]
    citations: list[CitationResponse]
    verification: dict = Field(default_factory=dict)


class AnalysisResponse(ResponseModel):
    id: str
    analysis_id: str
    job_id: str
    status: str
    created_at: str
    source_ids: list[str]
    sources: list[SourceResponse]
    coverage: dict
    limitations: list[str]
    findings_count: int
    model_calls: list[dict]


class JobResponse(ResponseModel):
    id: str
    job_id: str
    state: str
    stage: str
    progress: dict
    error: str | None
    attempts: int
    result: dict


class ProviderResponse(BaseModel):
    name: str
    model: str
    configured: bool


class ProfileResponse(BaseModel):
    language: Language = "en"
    id: str
    email: str | None
    is_guest: bool
    csrf_token: str
    retention_days: int
    preferred_provider: str
    authorized_providers: list[str] | None = None
    verified: bool
    providers: list[ProviderResponse]


class MessageResponse(BaseModel):
    message: str


class JobCreated(BaseModel):
    job_id: str


class SourceCreated(JobCreated):
    source_id: str


class AnalysisCreated(JobCreated):
    analysis_id: str


class QuestionResponse(ResponseModel):
    answer: str
    citations: list[CitationResponse]
    limitations: list[str]


class ConversationResponse(QuestionResponse):
    question: str
    created_at: str


class DashboardResponse(BaseModel):
    counts: dict[str, int]
    recent_documents: list[SourceResponse]
    recent_activity: list[dict[str, str]]


class ReportResponse(BaseModel):
    id: str
    format: Literal["json", "pdf"]
    sha256: str
    created_at: str


class RenameInput(Strict):
    name: str = Field(min_length=1, max_length=255)


class DiscoveryResponse(ResponseModel):
    job_id: str
    state: str
    error: str | None = None
    candidates: list[dict] = Field(default_factory=list)
    missing_categories: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
