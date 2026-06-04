from django import template

register = template.Library()


@register.filter
def dictget(d, key):
    """Look up a dict by a variable key in templates: {{ mydict|dictget:day }}."""
    if hasattr(d, "get"):
        return d.get(key, [])
    return []
