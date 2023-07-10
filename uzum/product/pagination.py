from rest_framework import pagination


class ExamplePagination(pagination.PageNumberPagination):
    page_size = 20
