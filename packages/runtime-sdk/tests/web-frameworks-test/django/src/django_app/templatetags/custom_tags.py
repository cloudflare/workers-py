from django import template

register = template.Library()


@register.simple_tag
def greet(name):
    return f"Hello, {name}!"


@register.filter
def multiply(value, arg):
    return value * arg
