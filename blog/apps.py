from django.apps import AppConfig
from django.db.models.signals import post_migrate

SITE_DOMAIN = 'blog321.onrender.com'


def sync_site_domain(sender, **kwargs):
    """Har bir migratsiyadan keyin Site.domeyni avtomatik yangilaydi."""
    from django.contrib.sites.models import Site

    Site.objects.update_or_create(
        id=1,
        defaults={'domain': SITE_DOMAIN, 'name': SITE_DOMAIN},
    )


class BlogConfig(AppConfig):
    name = 'blog'

    def ready(self):
        post_migrate.connect(sync_site_domain, sender=self)
