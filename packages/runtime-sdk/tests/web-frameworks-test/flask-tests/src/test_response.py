from flask import Response as FlaskResponse

from workers import FetchResponse, Response


def test_fetch_response_headers():
    fetch_response = Response(headers={"X-Workers-Test": "value"})

    assert isinstance(fetch_response, FetchResponse)

    flask_response = FlaskResponse(headers=fetch_response.headers)

    assert flask_response.headers["X-Workers-Test"] == "value"
