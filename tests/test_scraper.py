import pytest
from scraper.skroutz import _parse_search_results_json

def test_parse_search_results_json():
    # Mock data directly from user description
    data = {
        "skus": [
            {
                "future": False,
                "id": 59037954,
                "category_id": 40,
                "sku_url": "/s/59037954/Xiaomi-15-Ultra-5G-16-512GB-Silver-Chrome.html",
                "reviews_count": 58,
                "shop_count": 1,
                "review_score": "4,7",
                "price": "1.347,78 €",
                "name": "Xiaomi 15 Ultra 5G (16/512GB) Silver Chrome",
            },
            {
                "future": False,
                "id": 63191310,
                "category_id": 40,
                "sku_url": "/s/63191310/xiaomi-15t-5g-dual-sim-12-256gb-gray.html",
                "reviews_count": 52,
                "shop_count": 1,
                "review_score": "4,7",
                "price": "436,17 €",
                "name": "Xiaomi 15T 5G Dual SIM",
            }
        ]
    }

    # Query matching the first result (very close)
    query = "Xiaomi 15 Ultra"
    result = _parse_search_results_json(data, query)

    assert result is not None
    assert result.found is True
    assert result.product_name == "Xiaomi 15 Ultra 5G (16/512GB) Silver Chrome"
    assert result.lowest_price == 1347.78
    assert result.shop_count == 1
    assert result.rating == 4.7
    assert result.review_count == 58
    assert result.product_url == "https://www.skroutz.gr/s/59037954/Xiaomi-15-Ultra-5G-16-512GB-Silver-Chrome.html"
    assert getattr(result, "skroutz_id") == 59037954

def test_parse_search_results_json_no_results():
    data = {
        "skus": []
    }
    result = _parse_search_results_json(data, "Something")
    assert result is None

def test_parse_search_results_json_bad_price():
    data = {
        "skus": [
            {
                "id": 123,
                "price": "Call for price",
                "name": "Xiaomi 15 Ultra",
                "sku_url": "/s/123/x.html"
            }
        ]
    }
    result = _parse_search_results_json(data, "Xiaomi 15 Ultra")
    assert result is not None
    assert result.lowest_price == 0.0
    assert getattr(result, "skroutz_id") == 123
