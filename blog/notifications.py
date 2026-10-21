from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from allauth.socialaccount.models import SocialAccount

from .models import Notification


def _actor_avatar_url(actor):
    default_avatar = actor._meta.get_field('avatar').get_default()
    if actor.avatar and actor.avatar.name != default_avatar:
        try:
            return actor.avatar.url
        except ValueError:
            pass
    google_account = SocialAccount.objects.filter(
        user=actor,
        provider='google',
    ).first()
    if google_account and google_account.extra_data:
        picture = google_account.extra_data.get('picture')
        if picture and picture.startswith('https://'):
            return picture
    return static('images/avatar-default.svg')


def _target_url(notification):
    if notification.verb == Notification.Verb.MESSAGE:
        return reverse('chat_conversation', args=[notification.conversation_id])
    if notification.verb in (Notification.Verb.LIKE, Notification.Verb.COMMENT):
        return reverse('post_detail', args=[notification.post_id])
    return reverse('public_profile', args=[notification.actor_id])


def _render_text(notification):
    actor_name = notification.actor.get_full_name() or notification.actor.username
    if notification.verb == Notification.Verb.LIKE:
        return 'postingizga like bosdi'
    if notification.verb == Notification.Verb.COMMENT:
        return 'postingizga izoh qoldirdi'
    if notification.verb == Notification.Verb.FOLLOW:
        return 'sizni kuzata boshladi'
    return 'sizga yangi xabar yubordi'


def serialize_notification(notification):
    actor_name = notification.actor.get_full_name() or notification.actor.username
    text = _render_text(notification)
    preview = notification.preview or ''
    return {
        'id': str(notification.pk),
        'verb': notification.verb,
        'actor_id': str(notification.actor_id),
        'actor_name': actor_name,
        'actor_url': reverse('public_profile', args=[notification.actor_id]),
        'avatar_url': _actor_avatar_url(notification.actor),
        'text': text,
        'preview': preview[:160],
        'url': _target_url(notification),
        'is_read': notification.is_read,
        'created_at': timezone.localtime(notification.created_at).strftime(
            '%d.%m.%Y %H:%M',
        ),
        'created_at_iso': notification.created_at.isoformat(),
    }


def notify_group_name(recipient_pk):
    return f'notify_{recipient_pk}'


def push_notification(recipient, notification):
    """Notification obyektini recipient'ning websocket guruhiga jonli yuboradi."""
    payload = serialize_notification(notification)
    unread_count = Notification.objects.filter(
        recipient=recipient,
        is_read=False,
    ).count()
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return payload
    async_to_sync(channel_layer.group_send)(
        notify_group_name(recipient.pk),
        {
            'type': 'new_notification',
            'notification': payload,
            'unread_count': unread_count,
        },
    )
    return payload


def create_notification(*, recipient, actor, verb, post=None,
                       conversation=None, preview='', push=True):
    """Yangi notification yozadi va (kerak bo'lsa) recipient'ga jonli uzatadi."""
    if actor.pk == recipient.pk:
        return None

    if verb == Notification.Verb.LIKE:
        # Bir xil like Bildirishnomani qayta yaratmaslik uchun
        existing = Notification.objects.filter(
            recipient=recipient,
            actor=actor,
            verb=Notification.Verb.LIKE,
            post=post,
        ).first()
        if existing is not None:
            existing.is_read = False
            existing.save(update_fields=['is_read', 'updated_at'])
            if push:
                push_notification(recipient, existing)
            return existing

    notification = Notification.objects.create(
        recipient=recipient,
        actor=actor,
        verb=verb,
        post=post,
        conversation=conversation,
        preview=preview[:160],
    )
    if push:
        push_notification(recipient, notification)
    return notification
