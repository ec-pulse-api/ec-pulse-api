from app.services.research_ingest import detect_source


def test_detect_source_requires_real_domain_boundary():
    assert detect_source("www.amazon.co.jp") == "amazon"
    assert detect_source("evil-amazon.co.jp.example") == "generic"
    assert detect_source("shopping.yahoo.co.jp") == "yahoo"
    assert detect_source("evilshopping.yahoo.co.jp.example") == "generic"


import pytest
from app.services.research_ingest import fetch_public_comments

@pytest.mark.asyncio
async def test_research_comment_limit_is_bounded():
    with pytest.raises(ValueError, match="max_comments"):
        await fetch_public_comments("https://example.com", 501)
