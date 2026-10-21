from urllib.parse import urlsplit

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import Client, TransactionTestCase
from django.urls import reverse

from .consumers import NotificationConsumer
from .models import Notification, Post, Profile


class NotificationFlowTest(TransactionTestCase):
    """Like/izoh/kuzatish/chat xabar bildirishnomalari uchun testlar."""

    def setUp(self):
        self.alice = Profile.objects.create_user(
            username='alice_test',
            password='Strong-pass-123',
        )
        self.bob = Profile.objects.create_user(
            username='bob_test',
            password='Strong-pass-123',
        )
        self.post = Post.objects.create(
            author=self.alice,
            title='Test post',
            desc='matn',
        )
        self.bob_client = Client()
        self.bob_client.force_login(self.bob)
        self.alice_client = Client()
        self.alice_client.force_login(self.alice)

    def test_like_creates_notification_for_post_author(self):
        self.bob_client.post(
            f'/post/{self.post.id}/like/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(
            self.alice.received_notifications.filter(
                verb=Notification.Verb.LIKE,
            ).count(),
            1,
        )

    def test_unlike_does_not_create_notification(self):
        self.bob_client.post(f'/post/{self.post.id}/like/')
        self.bob_client.post(
            f'/post/{self.post.id}/like/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertFalse(
            self.alice.received_notifications.filter(
                verb=Notification.Verb.LIKE,
            ).exists(),
        )

    def test_comment_creates_notification_with_preview(self):
        self.bob_client.post(
            f'/post/{self.post.id}/comment/',
            {'text': 'Yaxshi post!'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        notification = self.alice.received_notifications.filter(
            verb=Notification.Verb.COMMENT,
        ).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.preview, 'Yaxshi post!')
        self.assertEqual(notification.post, self.post)

    def test_follow_creates_notification(self):
        self.bob_client.post(
            f'/user/{self.alice.id}/follow/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        notification = self.alice.received_notifications.filter(
            verb=Notification.Verb.FOLLOW,
        ).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.actor, self.bob)

    def test_unfollow_and_refollow_deduplicated_like_notification(self):
        self.bob_client.post(
            f'/post/{self.post.id}/like/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.bob_client.post(
            f'/post/{self.post.id}/like/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )  # unlike
        self.bob_client.post(
            f'/post/{self.post.id}/like/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )  # re-like
        self.assertEqual(
            self.alice.received_notifications.filter(
                verb=Notification.Verb.LIKE,
            ).count(),
            1,
        )

    def test_actor_is_not_notified_about_own_actions(self):
        self.alice_client.post(
            f'/post/{self.post.id}/like/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.alice_client.post(
            f'/post/{self.post.id}/comment/',
            {'text': "o'z izohim"},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertFalse(self.alice.received_notifications.exists())

    def test_notifications_data_api(self):
        self.bob_client.post(
            f'/post/{self.post.id}/comment/',
            {'text': 'Salom'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        response = self.alice_client.get(reverse('notifications_data'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['unread_count'], 1)
        self.assertEqual(len(data['notifications']), 1)
        notification = data['notifications'][0]
        self.assertEqual(notification['verb'], 'comment')
        self.assertEqual(notification['preview'], 'Salom')
        self.assertIn(
            str(self.post.id),
            urlsplit(notification['url']).path,
        )
        self.assertIn('/static/', notification['avatar_url'])

    def test_mark_all_read_api(self):
        self.bob_client.post(
            f'/post/{self.post.id}/comment/',
            {'text': 'Salom'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        response = self.alice_client.post(reverse('notifications_read'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 0)
        self.assertFalse(
            self.alice.received_notifications.filter(is_read=False).exists(),
        )

    def test_mark_single_read_api(self):
        self.bob_client.post(
            f'/post/{self.post.id}/comment/',
            {'text': 'Salom'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        notification = self.alice.received_notifications.first()
        response = self.alice_client.post(
            reverse('notifications_read'),
            {'id': str(notification.id)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 0)

    def test_notifications_apis_require_authentication(self):
        self.assertEqual(
            Client().get(reverse('notifications_data')).status_code,
            302,
        )
        self.assertEqual(
            Client().post(reverse('notifications_read')).status_code,
            302,
        )


class NotificationRealtimeTest(TransactionTestCase):
    """Jane websocketga ulanib, yaNGI bildirishnoman real-time oladi."""

    TIMEOUT = 5

    @database_sync_to_async
    def push_via_like(self):
        bob = Profile.objects.get(username='bob_test')
        post = Post.objects.filter(
            author__username='alice_test',
        ).first()
        client = Client()
        client.force_login(bob)
        client.post(
            f'/post/{post.id}/like/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    async def test_unread_count_on_connect_and_realtime_push(self):
        alice = await database_sync_to_async(Profile.objects.create_user)(
            username='alice_test',
            password='Strong-pass-123',
        )
        bob = await database_sync_to_async(Profile.objects.create_user)(
            username='bob_test',
            password='Strong-pass-123',
        )
        await database_sync_to_async(Post.objects.create)(
            author=alice,
            title='Test post',
            desc='matn',
        )

        # To'liq asgi stack'da auth headarda cookie bo'lishi kerak,
        # shuning uchun testda bevosita consumer'ni ishlatamiz.
        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(),
            '/ws/notify/',
        )
        communicator.scope['user'] = alice
        connected, close_code = await communicator.connect()
        self.assertTrue(connected)

        # Ulana ololmasa javob: joriy o'qilmaganlar soni.
        greeting = await communicator.receive_from(timeout=self.TIMEOUT)
        self.assertIn('unread_count', greeting)
        self.assertIn('0', greeting)

        await self.push_via_like()

        event = await communicator.receive_from(timeout=self.TIMEOUT)
        self.assertIn('new_notification', event)
        self.assertIn('"verb": "like"', event)

        await communicator.disconnect()
