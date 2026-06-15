from extract import parse_price, extract_items, map_to_structured


def test_parse_price_handles_symbols_and_junk():
    assert parse_price(None) == 0.0
    assert parse_price(3) == 3.0
    assert parse_price("$5.00") == 5.0
    assert parse_price("1,234.50") == 1234.50
    assert parse_price("abc") == 0.0


def test_extract_items_basic():
    menu = [
        {"nm": "Coffee", "cnt": "2", "price": "5.00"},
        {"nm": "Bagel", "cnt": "1", "price": "3.00"},
    ]
    assert extract_items(menu) == [
        {"description": "Coffee", "quantity": 2, "price": 5.00},
        {"description": "Bagel", "quantity": 1, "price": 3.00},
    ]


def test_extract_items_expands_unitprice_subitems():
    menu = [
        {
            "nm": "Combo",
            "cnt": "1",
            "price": "10.00",
            "unitprice": [
                {"nm": "Burger", "cnt": "1", "price": "6.00"},
                {"nm": "Fries", "cnt": "1", "price": "4.00"},
            ],
        }
    ]
    assert extract_items(menu) == [
        {"description": "Burger", "quantity": 1, "price": 6.00},
        {"description": "Fries", "quantity": 1, "price": 4.00},
    ]


def test_maps_total_tax_merchant_and_items():
    raw = {
        "menu": [
            {"nm": "Coffee", "cnt": "2", "price": "5.00"},
            {"nm": "Bagel", "cnt": "1", "price": "3.00"},
        ],
        "sub_total": {"subtotal_price": "8.00", "tax_price": "0.80"},
        "total": {"total_price": "8.80"},
    }
    result = map_to_structured(raw)
    assert result["total_amount"] == 8.80
    assert result["tax"] == 0.80
    assert result["merchant_name"] == "Coffee"
    assert result["items"] == [
        {"description": "Coffee", "quantity": 2, "price": 5.00},
        {"description": "Bagel", "quantity": 1, "price": 3.00},
    ]


def test_single_item_dict_is_normalized_to_list():
    raw = {"menu": {"nm": "Water", "cnt": "1", "price": "1.50"}, "total": {"total_price": "1.50"}}
    result = map_to_structured(raw)
    assert result["items"] == [{"description": "Water", "quantity": 1, "price": 1.50}]
    assert result["merchant_name"] == "Water"


def test_missing_fields_default_safely():
    result = map_to_structured({})
    assert result["items"] == []
    assert result["total_amount"] == 0.0
    assert result["tax"] == 0.0
    assert result["merchant_name"] == "Unknown"
    assert result["date"] is not None
