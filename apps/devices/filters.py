import django_filters as filters

from .models import Device


class DeviceFilter(filters.FilterSet):
    """Rich filtering for the device list / fleet view."""

    online = filters.BooleanFilter(method="filter_online")
    low_battery = filters.NumberFilter(field_name="battery_level", lookup_expr="lte")
    seen_after = filters.IsoDateTimeFilter(field_name="last_seen", lookup_expr="gte")
    group = filters.UUIDFilter(field_name="group__id")

    class Meta:
        model = Device
        fields = ("organization", "device_type", "status", "group", "manufacturer")

    def filter_online(self, queryset, name, value):
        from .models import DeviceStatus

        if value:
            return queryset.filter(status=DeviceStatus.ONLINE)
        return queryset.exclude(status=DeviceStatus.ONLINE)
