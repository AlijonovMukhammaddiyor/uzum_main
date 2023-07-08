from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class ShopsPagination(PageNumberPagination):
    page_size = 20
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = 1000

    def get_ordering(self, request, queryset, view):
        """
        Ordering is set by a comma delimited string.
        """
        ordering = super().get_ordering(request, queryset, view)

        # Remove 'id' from ordering if it exists
        if ordering:
            ordering = [field for field in ordering if field != "id"]

        return ordering

    def get_paginated_response(self, data):
        return Response(
            {
                "links": {"next": self.get_next_link(), "previous": self.get_previous_link()},
                "count": self.page.paginator.count,
                "results": data,
            }
        )
