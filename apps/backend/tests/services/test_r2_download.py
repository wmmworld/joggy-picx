import io
from unittest.mock import MagicMock, patch, ANY

from joggy.services import r2


def test_download_bytes_returns_content():
    fake_body = io.BytesIO(b"fake_jpeg_content")
    fake_client = MagicMock()
    fake_client.get_object.return_value = {"Body": fake_body}
    with patch("joggy.services.r2._get_client", return_value=fake_client):
        result = r2.download_bytes("events/abc/def/original.jpg")
    assert result == b"fake_jpeg_content"
    fake_client.get_object.assert_called_once_with(
        Bucket=ANY, Key="events/abc/def/original.jpg"
    )


def test_download_bytes_uses_correct_bucket():
    fake_body = io.BytesIO(b"data")
    fake_client = MagicMock()
    fake_client.get_object.return_value = {"Body": fake_body}
    with patch("joggy.services.r2._get_client", return_value=fake_client), \
         patch("joggy.services.r2.get_settings") as mock_settings:
        mock_settings.return_value.r2_bucket_name = "my-bucket"
        r2.download_bytes("some/key.jpg")
    fake_client.get_object.assert_called_once_with(
        Bucket="my-bucket", Key="some/key.jpg"
    )
