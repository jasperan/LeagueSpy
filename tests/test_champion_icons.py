"""Tests for champion icon URL resolution and download."""

import pytest

from src.champion_icons import get_icon_url, normalize_champion_name


class TestNormalizeChampionName:
    def test_simple_name(self):
        assert normalize_champion_name("Jinx") == "Jinx"

    def test_space_removal(self):
        assert normalize_champion_name("Lee Sin") == "LeeSin"

    def test_wukong_special_case(self):
        assert normalize_champion_name("Wukong") == "MonkeyKing"

    def test_renata_glasc(self):
        assert normalize_champion_name("Renata Glasc") == "Renata"

    def test_nunu_and_willump(self):
        assert normalize_champion_name("Nunu & Willump") == "Nunu"

    def test_khazix_apostrophe(self):
        assert normalize_champion_name("Kha'Zix") == "Khazix"

    def test_chogath(self):
        assert normalize_champion_name("Cho'Gath") == "Chogath"

    def test_belveth(self):
        assert normalize_champion_name("Bel'Veth") == "Belveth"

    def test_kaisa(self):
        assert normalize_champion_name("Kai'Sa") == "Kaisa"

    def test_velkoz(self):
        assert normalize_champion_name("Vel'Koz") == "Velkoz"

    def test_unknown_returns_cleaned(self):
        assert normalize_champion_name("Some New Champ") == "SomeNewChamp"


class TestGetIconUrl:
    def test_returns_ddragon_url(self):
        url = get_icon_url("Jinx", version="14.6.1")
        assert url == "https://ddragon.leagueoflegends.com/cdn/14.6.1/img/champion/Jinx.png"

    def test_normalizes_name(self):
        url = get_icon_url("Lee Sin", version="14.6.1")
        assert url == "https://ddragon.leagueoflegends.com/cdn/14.6.1/img/champion/LeeSin.png"
