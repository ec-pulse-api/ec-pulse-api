from app.services.product_parser import _find_product, _offers_dict


def test_offers_dict_accepts_list_and_prefers_priced_offer():
    offers = [{"availability": "InStock"}, {"price": "1980", "priceCurrency": "JPY"}]
    assert _offers_dict(offers)["price"] == "1980"


def test_find_product_accepts_array_type_and_graph():
    items = [
        {"@graph": [{"@type": ["Product", "Thing"], "name": "Test Product"}]}
    ]
    assert _find_product(items)["name"] == "Test Product"
