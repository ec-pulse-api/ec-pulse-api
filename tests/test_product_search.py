import pytest

from app.services.product_search import _yahoo_item_to_product


def test_yahoo_item_is_normalized_to_ec_pulse_shape():
    item = {
        "name": "Test Product",
        "description": "Description",
        "url": "https://shopping.yahoo.co.jp/item/test",
        "code": "seller-item-1",
        "price": 3980,
        "priceLabel": {"taxable": True, "defaultPrice": 3980},
        "janCode": "4900000000000",
        "brand": {"id": 10, "name": "Test Brand"},
        "seller": {
            "sellerId": "store1",
            "name": "Test Store",
            "url": "https://store.shopping.yahoo.co.jp/store1/",
        },
        "review": {
            "rate": 4.5,
            "count": 120,
            "url": "https://shopping.yahoo.co.jp/review/item/list?store_id=store1",
        },
        "inStock": True,
        "image": {"medium": "https://example.com/image.jpg"},
    }

    result = _yahoo_item_to_product(item)

    assert result["product"]["title"] == "Test Product"
    assert result["product"]["brand"] == "Test Brand"
    assert result["product"]["jan_code"] == "4900000000000"
    assert result["pricing"]["price"] == 3980
    assert result["pricing"]["currency"] == "JPY"
    assert result["source"]["marketplace"] == "yahoo"
    assert result["source"]["seller_id"] == "store1"
    assert result["review"]["rating"] == 4.5
    assert result["review"]["url"].startswith("https://shopping.yahoo.co.jp/review/")


def test_yahoo_item_falls_back_to_default_price():
    item = {
        "name": "Sale Product",
        "priceLabel": {"defaultPrice": 5000},
    }

    result = _yahoo_item_to_product(item)

    assert result["pricing"]["price"] == 5000
