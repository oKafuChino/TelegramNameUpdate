"""Built-in Bio templates.

Fork users can still add templates here, but installed users should prefer
/var/lib/tg_updater/bio_custom_templates.py so updates do not overwrite them.
"""


def elapsed_en(ctx):
    generated = (
        f"It lasted {ctx['years']} years "
        f"{ctx['months']} months and {ctx['days']} days"
    )
    format_letters = ctx.get("letters", str)
    return f"{format_letters(generated)} | {ctx['fixed_bio']}"


BIO_TEMPLATES = {
    "elapsed_en": {
        "name": "It lasted...",
        "description": "Default English elapsed time plus fixed Bio",
        "render": elapsed_en,
    },
}


def render_bio(template_name, ctx):
    import bio_template_loader

    return bio_template_loader.render_bio(template_name, ctx)
