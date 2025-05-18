from setuptools import setup, find_packages

setup(
    name="altbuilder",
    version="0.2.0",
    packages=find_packages(),
    install_requires=["loguru", "pyyaml", "click"],
    entry_points={"console_scripts": ["altbuilder = altbuilder.cli:cli"]},
    package_data={"altbuilder": ["config/default_config.yaml"]},
)
