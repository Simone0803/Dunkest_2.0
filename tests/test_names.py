from dunkest.names import player_key, player_surname


def test_player_key_strips_accents_and_suffixes():
    assert player_key("Nikola Jokić") == player_key("Nikola Jokic")
    assert player_key("Luka Dončić") == player_key("Luka Doncic")
    assert player_key("Karl-Anthony Towns") == player_key("Karl-anthony Towns")
    assert player_key("Ron Holland II") == player_key("Ron Holland")
    assert player_surname("Jimmy Butler Jr.") == "butler"
