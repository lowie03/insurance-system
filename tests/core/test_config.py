from insurance_core import catalogue, config


def test_every_config_file_has_a_version():
    versions = config.versions()
    assert set(versions) == set(config.CONFIG_FILES)
    assert all(versions.values())


def test_every_product_has_pricing_and_eligibility_rules():
    codes = set(catalogue.products())
    assert codes == set(config.load("pricing")["products"])
    assert codes == set(config.load("eligibility_rules")["rules"])


def test_product_names():
    assert catalogue.product_name("HMC") == "Micro Health (Basic)"
    assert catalogue.product_name("UNKNOWN") == "UNKNOWN"