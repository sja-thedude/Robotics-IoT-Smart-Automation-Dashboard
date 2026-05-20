from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Page-number pagination with a client-tunable, capped page size."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500
