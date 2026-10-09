from django import template

from apps.portal.permissions import can

register = template.Library()


@register.filter(name="can")
def can_filter(user, spec):
    """{% if request.user|can:"courses.view" %}"""
    resource, _, action = spec.partition(".")
    return can(user, resource, action or "view")
