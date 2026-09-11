"""The exact shape of every request and response. FastAPI validates requests against these
before any of our code runs, and rejects bad input with a clear 422 error."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from insurance_core.features import MODEL_PRODUCTS

VehicleType = Literal["Saloon Car", "SUV", "Bus", "Tricycle", "Motorcycle"]


class ProfileIn(BaseModel):
    """Form answers. extra="forbid" rejects unknown fields, so a typo in the frontend fails loudly."""
    model_config = ConfigDict(extra="forbid")

    gender: Literal["Male", "Female"]
    age: int = Field(ge=18, le=100)
    marital_status: Literal["Married", "Single"]
    dependents: int = Field(ge=0, le=20)
    state: str = Field(min_length=2, max_length=40)
    geo_zone: Literal["North Central", "North East", "North West", "South East", "South South", "South West"]
    area_type: Literal["Urban", "Rural"]
    occupation: str = Field(min_length=2, max_length=60)
    occupation_category: Literal["Self-employed", "Public sector", "Private salaried", "Dependent", "Retired"]
    monthly_income_ngn: float | None = Field(default=None, ge=0)        # optional: people may skip it
    employer_hmo: bool = False
    smoker: bool = False
    pre_existing_condition: bool = False
    owns_vehicle: bool = False
    vehicle_type: VehicleType | None = None
    vehicle_year: int | None = Field(default=None, ge=1970, le=date.today().year + 1)
    vehicle_value_ngn: float | None = Field(default=None, gt=0)
    vehicle_use: Literal["Private", "Commercial"] | None = None
    home_status: Literal["Owner", "Renter", "Family house"]
    property_value_ngn: float | None = Field(default=None, gt=0)
    runs_shop: bool = False
    foreign_trips_per_year: int = Field(default=0, ge=0, le=50)
    risk_appetite: Literal["Low", "Medium", "High"] = "Medium"
    owned_products: list[str] = Field(default_factory=list)            # policies they already hold

    @model_validator(mode="after")
    def check_consistency(self):
        """Cross-field rules a single Field() can't express."""
        vehicle_fields = [self.vehicle_type, self.vehicle_year, self.vehicle_value_ngn, self.vehicle_use]
        if self.owns_vehicle and any(v is None for v in vehicle_fields):
            raise ValueError("vehicle_type, vehicle_year, vehicle_value_ngn and vehicle_use are required "
                             "when owns_vehicle is true")
        if not self.owns_vehicle:
            self.vehicle_type = self.vehicle_year = self.vehicle_value_ngn = self.vehicle_use = None
        if self.home_status != "Owner":
            self.property_value_ngn = None
        unknown = set(self.owned_products) - set(MODEL_PRODUCTS) - {"HMC"}
        if unknown:
            raise ValueError(f"unknown products in owned_products: {sorted(unknown)}")
        return self

    def to_core_profile(self) -> dict:
        """The plain dict insurance_core expects, with one 0/1 column per product."""
        data = self.model_dump(exclude={"owned_products"})
        for product in MODEL_PRODUCTS + ["HMC"]:
            data[product] = 1 if product in self.owned_products else 0
        return data


class QuoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=100)
    email: str | None = Field(default=None, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9]{10,14}$")
    profile: ProfileIn


class BreakdownStep(BaseModel):
    step: str
    running_total_ngn: float


class PaymentOption(BaseModel):
    plan: str
    payments: int
    payment_ngn: float
    total_ngn: float
    fits_budget: bool
    fits_cash_flow: bool


class RecommendationOut(BaseModel):
    product: str
    product_name: str
    match_score: float
    premium_ngn: float
    breakdown: list[BreakdownStep]
    payment_options: list[PaymentOption]
    suggested_plan: str
    notes: list[str]


class ExclusionOut(BaseModel):
    product: str
    product_name: str
    kind: Literal["eligibility", "affordability"]
    reason: str


class QuoteOut(BaseModel):
    quote_id: str
    customer_id: str
    expires_at: str
    recommendations: list[RecommendationOut]
    excluded: list[ExclusionOut]
    refer_to_broker: bool
    refer_reason: str | None


class PolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [
        {"quote_id": "paste-the-quote_id-here", "product_code": "HCN", "payment_reference": "SIM-TEST-1"}
    ]})

    quote_id: str
    product_code: str
    payment_reference: str
    payment_plan: str | None = None    # None -> issuance picks the quote's suggested_plan


class PolicyOut(BaseModel):
    policy_number: str
    customer_id: str
    product_code: str
    product_name: str
    premium_ngn: float
    payment_plan: str
    payment_ngn: float
    total_ngn: float
    start_date: str
    end_date: str
    status: str
    signature: str
    certificate_url: str
    verify_url: str


class VerificationOut(BaseModel):
    """Public: shows as little as possible. No names, no amounts, no contact details."""
    status: str
    product_name: str | None = None
    valid_until: str | None = None