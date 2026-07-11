"""User-extensible Bio templates.

Fork users can add a new function and register it in BIO_TEMPLATES.
Each template receives a context dict with years, months, days,
birth_date, today and fixed_bio.
"""


def elapsed_en(ctx):
    return (
        f"It lasted {ctx['years']} years "
        f"{ctx['months']} months and {ctx['days']} days | "
        f"{ctx['fixed_bio']}"
    )


BIO_TEMPLATES = {
    "elapsed_en": elapsed_en,
}


def render_bio(template_name, ctx):
    template = BIO_TEMPLATES.get(template_name) or BIO_TEMPLATES["elapsed_en"]
    value = template(ctx)
    if not isinstance(value, str):
        raise TypeError(f"Bio template {template_name!r} must return str")
    return value
