from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateChatStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(base_url=None)

    @property
    def location(self):
        return Path(settings.PRIVATE_CHAT_MEDIA_ROOT)

    def url(self, name):
        raise ValueError('Chat media must be served through the protected chat view.')
