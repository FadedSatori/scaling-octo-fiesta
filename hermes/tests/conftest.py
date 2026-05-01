import pytest

# Use asyncio mode so @pytest.mark.asyncio works on class methods too
pytest_plugins = ("pytest_asyncio",)
