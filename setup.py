from setuptools import setup, find_packages

setup(
    name="whacamole",
    version="1.0.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "whacamole = whacamole.cli:main",
        ],
    },
)
