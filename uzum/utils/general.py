from rest_framework.request import Request


def decode_request(request: Request, method: str) -> dict:
    """
    Decodes request body.
    Args:
        request (Request): _description_

    Returns:
        dict: decoded request body
    """
    if method == "GET":
        return request.query_params.dict()
    elif method == "POST":
        return request.data.dict()
    else:
        # just return empty dict
        return {}
