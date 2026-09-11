"""Shared test profiles. Values match customers from the Colab experiments,
so the tests lock in exactly the results we verified there."""
import pytest

BASE = {
    "gender": "Male", "state": "Lagos", "geo_zone": "South West", "area_type": "Urban",
    "employer_hmo": False, "smoker": False, "pre_existing_condition": False,
    "owns_vehicle": False, "vehicle_type": None, "vehicle_year": None,
    "vehicle_value_ngn": None, "vehicle_use": None, "property_value_ngn": None,
    "runs_shop": False, "foreign_trips_per_year": 0, "risk_appetite": "Medium",
}


@pytest.fixture
def trader():
    """NG-SYN-00021: married trader, 52, two dependents, owns his home."""
    return {**BASE, "customer_id": "NG-SYN-00021", "full_name": "Efe Olawale", "age": 52,
            "marital_status": "Married", "dependents": 2, "occupation": "Trader",
            "occupation_category": "Self-employed", "monthly_income_ngn": 112_000.0,
            "home_status": "Owner", "property_value_ngn": 17_490_000.0, "runs_shop": True}


@pytest.fixture
def unemployed():
    """NG-SYN-00008: single, 35, ₦5,000/month, renting."""
    return {**BASE, "customer_id": "NG-SYN-00008", "full_name": "Test Person", "age": 35,
            "marital_status": "Single", "dependents": 0, "occupation": "Unemployed",
            "occupation_category": "Dependent", "monthly_income_ngn": 5_000.0, "home_status": "Renter"}


@pytest.fixture
def bus_owner():
    """NG-SYN-00048: commercial bus worth ₦13.93m, ₦114,000/month."""
    return {**BASE, "customer_id": "NG-SYN-00048", "full_name": "Test Driver", "age": 40,
            "marital_status": "Married", "dependents": 3, "occupation": "Commercial Driver",
            "occupation_category": "Self-employed", "monthly_income_ngn": 114_000.0,
            "home_status": "Renter", "owns_vehicle": True, "vehicle_type": "Bus",
            "vehicle_year": 2015.0, "vehicle_value_ngn": 13_930_000.0, "vehicle_use": "Commercial"}