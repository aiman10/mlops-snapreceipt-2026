from extract import map_cord_to_schema


def test_maps_total_tax_and_items():
    cord = {
        "menu": [
            {"nm": "Coffee", "cnt": "2", "price": "5.00"},
            {"nm": "Bagel", "cnt": "1", "price": "3.00"},
        ],
        "sub_total": {"subtotal_price": "8.00", "tax_price": "0.80"},
        "total": {"total_price": "8.80"},
    }
    result = map_cord_to_schema(cord)
    assert result["total"] == 8.80
    assert result["tax"] == 0.80
    assert result["items"] == [
        {"description": "Coffee", "quantity": 2, "price": 5.00},
        {"description": "Bagel", "quantity": 1, "price": 3.00},
    ]


def test_single_item_dict_is_normalized_to_list():
    cord = {"menu": {"nm": "Water", "cnt": "1", "price": "1.50"}, "total": {"total_price": "1.50"}}
    result = map_cord_to_schema(cord)
    assert result["items"] == [{"description": "Water", "quantity": 1, "price": 1.50}]
    assert result["tax"] is None


def test_missing_fields_default_safely():
    result = map_cord_to_schema({})
    assert result["items"] == []
    assert result["total"] is None
    assert result["merchant"] == "Unknown"
    assert result["date"] is not None
