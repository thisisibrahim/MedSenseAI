from typing import Literal

from pydantic import BaseModel, Field


class ParsedTestResult(BaseModel):
    test_name: str = Field(..., description="Name of the medical test")
    value: str = Field(default="", description="Observed value from the report")
    flag: str = Field(default="", description="Report flag such as LOW, HIGH, BORDERLINE, if available")
    unit: str = Field(default="", description="Measurement unit, if available")
    reference_range: str = Field(default="", description="Reference range printed in the report, if available")
    status: Literal["low", "normal", "high", "borderline", "unknown"] = "unknown"


class ParsedMedicalReport(BaseModel):
    report_type: str = Field(default="Unknown", description="Detected medical report type")
    patient_age: str = Field(default="", description="Patient age, if available")
    patient_gender: str = Field(default="", description="Patient gender, if available")
    tests: list[ParsedTestResult] = Field(default_factory=list)

    parser_mode: str = Field(
        default="unknown",
        description="Parser used: gemini, regex_fallback, or no_api_key_regex"
    )

    parser_message: str = Field(
        default="",
        description="Short parser diagnostic message for debugging"
    )