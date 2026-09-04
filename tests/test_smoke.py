def test_top_level_packages_import() -> None:
    import application
    import domain

    assert domain is not None
    assert application is not None


def test_package_metadata() -> None:
    from importlib.metadata import version

    assert version("agentic-conclave") == "0.1.0"
