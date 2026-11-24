from strainforge import config


def test_team_price_includes_three_engineers():
    for n in (1, 2, 3):
        assert config.team_price_cents(n) == 4999
        assert config.team_price_cents(n, yearly=True) == 54900


def test_extra_engineers():
    assert config.team_price_cents(5) == 4999 + 2 * 1499
    assert config.team_price_cents(5, yearly=True) == 54900 + 2 * 16400


def test_yearly_is_one_month_free():
    pairs = [(config.PRICE_PERSONAL_CENTS, config.PRICE_PERSONAL_YEAR_CENTS),
             (config.PRICE_TEAM_CENTS, config.PRICE_TEAM_YEAR_CENTS),
             (config.PRICE_SEAT_CENTS, config.PRICE_SEAT_YEAR_CENTS)]
    for month, year in pairs:
        assert 11 * month - 100 < year <= 11 * month


def test_team_engineer_never_costs_more_than_personal_from_three_up():
    for n in range(3, 30):
        assert config.team_price_cents(n) / n < config.PRICE_PERSONAL_CENTS
