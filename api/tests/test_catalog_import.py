import io

from openpyxl import Workbook

from app.catalog import ColumnMapping, OptionCol, convert, parse_delimited, parse_number, parse_xlsx


def test_parse_number_variants():
    assert parse_number("۱,۲۵۰,۰۰۰") == 1250000
    assert parse_number("450000 تومان") == 450000
    assert parse_number("450 هزار تومان") == 450000
    assert parse_number("۲ میلیون") == 2000000
    assert parse_number("1٬250٬000") == 1250000
    assert parse_number("12.5 هزار") == 12500
    assert parse_number("") is None and parse_number("تماس بگیرید") is None


def test_parse_delimited_sniffs_tabs_and_semicolons():
    assert parse_delimited("نام\tقیمت\nشال\t90000\n") == [["نام", "قیمت"], ["شال", "90000"]]
    assert parse_delimited("نام;قیمت\nشال;90000\n")[1] == ["شال", "90000"]


def test_parse_xlsx_reads_numbers_as_clean_strings():
    wb = Workbook()
    ws = wb.active
    ws.append(["نام", "قیمت", "موجودی"])
    ws.append(["شال", 90000.0, 4])
    buf = io.BytesIO()
    wb.save(buf)
    assert parse_xlsx(buf.getvalue()) == [["نام", "قیمت", "موجودی"], ["شال", "90000", "4"]]


def test_convert_units_stock_options_and_skips():
    rows = [["نام", "گروه", "قیمت", "موجودی", "سایز"],
            ["پیراهن", "مردانه", "450", "ناموجود", "S / M / L"],
            ["شلوار", "مردانه", "۶۰۰", "", "۴۰،۴۲"],
            ["بدون قیمت", "x", "تماس بگیرید", "", ""],
            ["", "", "", "", ""]]
    m = ColumnMapping(header_row=0, name_col=0, category_col=1, price_col=2, price_unit="thousand_toman", stock_col=3,
                      description_col=None, option_cols=[OptionCol(group="سایز", column=4, separator="/")], notes=[])
    products, warnings = convert(rows, m)
    assert [p["price"] for p in products] == [450000, 600000]
    assert products[0]["stock"] == 0 and products[1]["stock"] is None
    assert products[0]["options"] == [{"name": "سایز", "choices": ["S", "M", "L"]}]
    assert products[1]["options"][0]["choices"] == ["۴۰", "۴۲"]
    assert any("بدون قیمت" in w or "1 ردیف" in w for w in warnings)


def test_rial_prices_are_divided_by_ten():
    m = ColumnMapping(header_row=None, name_col=0, category_col=None, price_col=1, price_unit="rial", stock_col=None,
                      description_col=None, option_cols=[], notes=[])
    products, _ = convert([["شال", "900000"]], m)
    assert products[0]["price"] == 90000


def test_size_ranges_are_expanded_keeping_digit_script():
    from app.catalog import clean_options, expand_ranges

    assert expand_ranges(["۴۰ تا ۴۴"]) == ["۴۰", "۴۱", "۴۲", "۴۳", "۴۴"]
    assert expand_ranges(["38-40", "M"]) == ["38", "39", "40", "M"]
    assert expand_ranges(["۱ تا ۱۰۰۰"]) == ["۱ تا ۱۰۰۰"]  # absurd ranges are left alone
    assert clean_options([{"name": "سایز", "choices": ["۴۰ تا ۴۲"]}, {"name": "رنگ", "choices": []}]) == [{"name": "سایز", "choices": ["۴۰", "۴۱", "۴۲"]}]


def test_word_separator_does_not_break_ranges_in_table_import():
    """Regression: the model named «تا» as the separator and the old code split on the letters ت and ا."""
    rows = [["نام", "قیمت", "سایز"], ["کفش کتانی", "2800", "۴۰ تا ۴۴"], ["کفش چرم", "3500", "۴۰ / ۴۲"]]
    m = ColumnMapping(header_row=0, name_col=0, category_col=None, price_col=1, price_unit="toman", stock_col=None,
                      description_col=None, option_cols=[OptionCol(group="سایز", column=2, separator="تا")], notes=[])
    products, _ = convert(rows, m)
    assert products[0]["options"][0]["choices"] == ["۴۰", "۴۱", "۴۲", "۴۳", "۴۴"]
    assert products[1]["options"][0]["choices"] == ["۴۰", "۴۲"]
