"""Tests for champion icon URL resolution and download."""

from unittest.mock import patch, MagicMock
from io import BytesIO

from src.champion_icons import get_icon_url, normalize_champion_name, download_icon


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


class TestDownloadIcon:
    @patch("src.champion_icons.httpx")
    def test_download_and_cache(self, mock_httpx, tmp_path):
        from PIL import Image as PILImage

        # Create a tiny valid PNG in memory
        img = PILImage.new("RGBA", (120, 120), (255, 0, 0, 255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        mock_resp = MagicMock()
        mock_resp.content = png_bytes
        mock_resp.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_resp

        with patch("src.champion_icons.ICON_CACHE_DIR", tmp_path):
            with patch("src.champion_icons.fetch_ddragon_version", return_value="14.6.1"):
                result = download_icon("Jinx", size=48)

        assert result is not None
        assert result.size == (48, 48)
        assert (tmp_path / "Jinx_48.png").exists()

    @patch("src.champion_icons.httpx")
    def test_returns_none_on_http_error(self, mock_httpx):
        mock_httpx.get.side_effect = Exception("network error")

        with patch("src.champion_icons.fetch_ddragon_version", return_value="14.6.1"):
            result = download_icon("Jinx", size=48)

        assert result is None

    def test_returns_cached_icon(self, tmp_path):
        from PIL import Image as PILImage

        # Pre-populate cache
        img = PILImage.new("RGBA", (48, 48), (0, 255, 0, 255))
        cache_file = tmp_path / "Jinx_48.png"
        img.save(cache_file, format="PNG")

        with patch("src.champion_icons.ICON_CACHE_DIR", tmp_path):
            result = download_icon("Jinx", size=48)

        assert result is not None
        assert result.size == (48, 48)
