import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from .models import Conversation, DirectMessage, Notification
from .notifications import create_notification, notify_group_name
from .views import _avatar_url_for_user


PRESENCE_TIMEOUT = 90


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return

        conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.conversation = await self.get_conversation(conversation_id)
        if self.conversation is None:
            await self.close(code=4404)
            return

        self.peer = await self.get_peer()
        self.group_name = f'chat_{self.conversation.pk.hex}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.change_presence(1)
        await self.send_json({
            'type': 'presence',
            'user_id': str(self.peer.pk),
            'online': await self.is_online(self.peer.pk),
        })
        await self.channel_layer.group_send(self.group_name, {
            'type': 'presence_changed',
            'user_id': str(self.user.pk),
            'online': True,
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )
        if hasattr(self, 'user') and self.user.is_authenticated:
            online = await self.change_presence(-1)
            if hasattr(self, 'group_name') and not online:
                await self.channel_layer.group_send(self.group_name, {
                    'type': 'presence_changed',
                    'user_id': str(self.user.pk),
                    'online': False,
                })

    async def receive_json(self, content, **kwargs):
        event_type = content.get('type')
        if event_type == 'heartbeat':
            await self.change_presence(0)
            return

        if event_type == 'typing':
            await self.channel_layer.group_send(self.group_name, {
                'type': 'typing_changed',
                'user_id': str(self.user.pk),
                'typing': bool(content.get('typing')),
            })
            return

        if event_type == 'edit_message':
            message_id = content.get('message_id')
            text = content.get('text')
            if not self.valid_message_id(message_id):
                await self.send_error('Tahrirlanadigan xabar topilmadi.')
                return
            if not isinstance(text, str) or not text.strip():
                await self.send_error('Xabar matni bo‘sh bo‘lmasligi kerak.')
                return
            if len(text.strip()) > 5000:
                await self.send_error('Xabar 5000 belgidan oshmasligi kerak.')
                return
            result = await self.edit_message(message_id, text.strip())
            if result is None:
                await self.send_error(
                    'Faqat o‘zingiz yuborgan matnli xabarni tahrirlashingiz mumkin.',
                )
                return
            await self.channel_layer.group_send(self.group_name, {
                'type': 'message_updated',
                'message': result,
            })
            return

        if event_type == 'delete_message':
            message_id = content.get('message_id')
            if not self.valid_message_id(message_id):
                await self.send_error('O‘chiriladigan xabar topilmadi.')
                return
            result = await self.delete_message(message_id)
            if result is None:
                await self.send_error(
                    'Faqat o‘zingiz yuborgan xabarni o‘chirishingiz mumkin.',
                )
                return
            await self.channel_layer.group_send(self.group_name, {
                'type': 'message_deleted',
                'message_id': message_id,
                'last_message': result['last_message'],
            })
            return

        if event_type != 'message':
            await self.send_error('Noma’lum chat amali.')
            return

        text = content.get('text')
        if not isinstance(text, str) or not text.strip():
            await self.send_error('Xabar matni bo‘sh bo‘lmasligi kerak.')
            return
        if len(text) > 5000:
            await self.send_error('Xabar 5000 belgidan oshmasligi kerak.')
            return

        message = await self.save_message(text.strip())
        await self.send_message_notification(message)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'message_created',
            'message': message,
        })

    @database_sync_to_async
    def send_message_notification(self, message):
        # Agar suhbatdosh shu suhbatni ochib turgan bo'lsa (presence > 0),
        # alohida notification yubormaymiz — u xabarni ko'rib turibdi.
        if cache.get(f'chat:presence:{self.peer.pk}', 0) > 0:
            return
        create_notification(
            recipient=self.peer,
            actor=self.user,
            verb=Notification.Verb.MESSAGE,
            conversation=self.conversation,
            preview=message.get('text', ''),
        )

    async def message_created(self, event):
        message = event['message']
        if message['sender_id'] != str(self.user.pk):
            await self.mark_message_read(message['id'])
        await self.send_json({
            'type': 'message',
            'message': message,
        })

    async def message_updated(self, event):
        await self.send_json({
            'type': 'message_updated',
            'message': event['message'],
        })

    async def message_deleted(self, event):
        await self.send_json({
            'type': 'message_deleted',
            'message_id': event['message_id'],
            'last_message': event['last_message'],
        })

    async def typing_changed(self, event):
        if event['user_id'] != str(self.user.pk):
            await self.send_json({
                'type': 'typing',
                'typing': event['typing'],
            })

    async def presence_changed(self, event):
        if event['user_id'] != str(self.user.pk):
            await self.send_json({
                'type': 'presence',
                'user_id': event['user_id'],
                'online': event['online'],
            })

    async def send_error(self, message):
        await self.send_json({
            'type': 'error',
            'message': message,
        })

    @staticmethod
    def valid_message_id(message_id):
        if not isinstance(message_id, str):
            return False
        try:
            uuid.UUID(message_id)
        except ValueError:
            return False
        return True

    @database_sync_to_async
    def get_conversation(self, conversation_id):
        try:
            conversation = Conversation.objects.select_related(
                'participant_a',
                'participant_b',
            ).get(pk=conversation_id)
        except Conversation.DoesNotExist:
            return None
        if self.user.pk not in (
            conversation.participant_a_id,
            conversation.participant_b_id,
        ):
            return None
        return conversation

    @database_sync_to_async
    def get_peer(self):
        return self.conversation.participant_for(self.user)

    @database_sync_to_async
    def save_message(self, text):
        message = DirectMessage.objects.create(
            conversation=self.conversation,
            sender=self.user,
            text=text,
        )
        Conversation.objects.filter(pk=self.conversation.pk).update(
            updated_at=message.created_at,
        )
        return {
            'id': str(message.pk),
            'text': message.text,
            'message_type': message.message_type,
            'media_url': (
                reverse('chat_media_file', args=[message.pk, message.message_type])
                if message.message_type != DirectMessage.MessageType.TEXT
                else None
            ),
            'sender_id': str(self.user.pk),
            'sender_name': self.user.get_full_name() or self.user.username,
            'avatar_url': _avatar_url_for_user(self.user),
            'created_at': timezone.localtime(message.created_at).strftime(
                '%H:%M',
            ),
            'created_at_iso': message.created_at.isoformat(),
        }

    @database_sync_to_async
    def mark_message_read(self, message_id):
        DirectMessage.objects.filter(
            pk=message_id,
            conversation=self.conversation,
            is_read=False,
        ).exclude(sender=self.user).update(is_read=True)

    @database_sync_to_async
    def edit_message(self, message_id, text):
        message = DirectMessage.objects.filter(
            pk=message_id,
            conversation=self.conversation,
            sender=self.user,
            message_type=DirectMessage.MessageType.TEXT,
        ).first()
        if message is None:
            return None
        message.text = text
        message.edited_at = timezone.now()
        message.save(update_fields=['text', 'edited_at', 'updated_at'])
        Conversation.objects.filter(pk=self.conversation.pk).update(
            updated_at=timezone.now(),
        )
        return {
            'id': str(message.pk),
            'text': message.text,
            'edited_at': timezone.localtime(message.edited_at).strftime(
                '%H:%M',
            ),
        }

    @database_sync_to_async
    def delete_message(self, message_id):
        message = DirectMessage.objects.filter(
            pk=message_id,
            conversation=self.conversation,
            sender=self.user,
        ).first()
        if message is None:
            return None

        if message.image:
            message.image.delete(save=False)
        if message.audio:
            message.audio.delete(save=False)
        message.delete()

        latest_message = self.conversation.messages.order_by(
            '-created_at',
        ).first()
        Conversation.objects.filter(pk=self.conversation.pk).update(
            updated_at=latest_message.created_at if latest_message else timezone.now(),
        )
        serialized_latest = None
        if latest_message is not None:
            serialized_latest = {
                'sender_id': str(latest_message.sender_id),
                'text': (
                    latest_message.text
                    if latest_message.message_type == DirectMessage.MessageType.TEXT
                    else '📷 Rasm'
                    if latest_message.message_type == DirectMessage.MessageType.IMAGE
                    else '🎤 Ovozli xabar'
                ),
                'created_at': timezone.localtime(
                    latest_message.created_at,
                ).strftime('%H:%M'),
                'id': str(latest_message.pk),
            }
        return {'last_message': serialized_latest}

    @database_sync_to_async
    def is_online(self, user_id):
        return cache.get(f'chat:presence:{user_id}', 0) > 0

    @database_sync_to_async
    def change_presence(self, amount):
        key = f'chat:presence:{self.user.pk}'
        current = cache.get(key, 0)
        updated = max(0, current + amount)
        if updated:
            cache.set(key, updated, timeout=PRESENCE_TIMEOUT)
        else:
            cache.delete(key)
        return updated > 0


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Foydalanuvchining shaxsiy bildirishnomalar kanali.

    Like, izoh, kuzatish va yangi shaxsiy xabarlar real-time Yetib boradi:
    guruhga yuborilgan har bir xabar shu yerdan foydalanuvchiga uzatiladi.
    """

    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close(code=4401)
            return
        self.group_name = notify_group_name(self.user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        unread_count = await self.get_unread_count()
        await self.send_json({
            'type': 'unread_count',
            'count': unread_count,
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def new_notification(self, event):
        await self.send_json({
            'type': 'new_notification',
            'notification': event['notification'],
            'unread_count': event['unread_count'],
        })

    async def unread_count_refreshed(self, event):
        await self.send_json({
            'type': 'unread_count',
            'count': event['count'],
        })

    @database_sync_to_async
    def get_unread_count(self):
        return Notification.objects.filter(
            recipient=self.user,
            is_read=False,
        ).count()
