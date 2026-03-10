"""Tests for PDF vision parser."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.plugins.sat_maestro.config import SatMaestroConfig
from src.plugins.sat_maestro.electrical.parsers.pdf_vision import PdfVisionParser, PdfVisionResult


@pytest.fixture
def config():
    return SatMaestroConfig(
        ollama_url="http://localhost:11434",
        vision_model="llava:13b",
        llm_vision_enabled=True,
    )


@pytest.fixture
def config_disabled():
    return SatMaestroConfig(llm_vision_enabled=False)


@pytest.fixture
def parser(config):
    return PdfVisionParser(config)


class TestPdfVisionParser:
    def test_parse_llm_json_direct(self):
        data = '{"components": [{"ref": "U1"}], "confidence": 0.9}'
        result = PdfVisionParser.parse_llm_json(data)
        assert result["confidence"] == 0.9

    def test_parse_llm_json_markdown_block(self):
        data = 'Some text\n```json\n{"components": [], "confidence": 0.8}\n```\nMore text'
        result = PdfVisionParser.parse_llm_json(data)
        assert result["confidence"] == 0.8

    def test_parse_llm_json_embedded_braces(self):
        data = 'Here is the result: {"components": [], "confidence": 0.7} end'
        result = PdfVisionParser.parse_llm_json(data)
        assert result["confidence"] == 0.7

    def test_parse_llm_json_invalid(self):
        result = PdfVisionParser.parse_llm_json("not json at all")
        assert result == {}

    @pytest.mark.asyncio
    async def test_disabled_vision(self, config_disabled, tmp_path):
        parser = PdfVisionParser(config_disabled)
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        result = await parser.parse(str(pdf))
        assert "disabled" in result.warnings[0].lower()

    @pytest.mark.asyncio
    async def test_file_not_found(self, parser):
        with pytest.raises(FileNotFoundError):
            await parser.parse("/nonexistent/file.pdf")

    @pytest.mark.asyncio
    async def test_analyze_page_ollama_call(self, parser):
        """Test that _analyze_page calls Ollama API correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "response": json.dumps({
                "components": [{"ref": "U1", "name": "MCU", "type": "IC", "pins": []}],
                "nets": [],
                "confidence": 0.85,
            })
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await parser._analyze_page(b"fake_image", "EPS", 1)

            assert len(result["components"]) == 1
            assert result["confidence"] == 0.85
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "llava:13b" in str(call_args)

    @pytest.mark.asyncio
    async def test_analyze_page_connection_error(self, parser):
        """Test handling of Ollama connection failure."""
        import httpx
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ConnectionError, match="Cannot connect to Ollama"):
                await parser._analyze_page(b"fake_image", "EPS", 1)

    @pytest.mark.asyncio
    async def test_analyze_page_bad_json_response(self, parser):
        """Test handling of non-JSON LLM response."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"response": "I cannot analyze this image properly."}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await parser._analyze_page(b"fake_image", "EPS", 1)
            assert result["components"] == []
            assert result["confidence"] == 0.0

    def test_config_has_ollama_fields(self):
        config = SatMaestroConfig.from_env()
        assert hasattr(config, "ollama_url")
        assert hasattr(config, "vision_model")
