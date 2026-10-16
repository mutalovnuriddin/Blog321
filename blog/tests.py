from django.test import TestCase
from django.test import TransactionTestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.utils import override_settings
import tempfile
from pathlib import Path
from django.contrib.auth import get_user_model
from django.urls import reverse
from allauth.socialaccount.models import SocialAccount, SocialApp
from django.contrib.sites.models import Site


class AuthenticationPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        site, _ = Site.objects.get_or_create(
            pk=1,
            defaults={'domain': 'example.com', 'name': 'example.com'},
        )
        social_app, _ = SocialApp.objects.get_or_create(
            provider='google',
            name='Google test',
            defaults={'client_id': 'test-client-id', 'secret': 'test-secret'},
        )
        social_app.sites.add(site)

    def test_login_and_register_pages_render(self):
        for page in ('login', 'register'):
            with self.subTest(page=page):
                response = self.client.get(reverse(page))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'auth.css')
                self.assertContains(response, 'Hisob')

    def test_registration_creates_user_and_logs_them_in(self):
        response = self.client.post(reverse('register'), {
            'username': 'sahifa_user',
            'email': 'user@example.com',
            'phone_number': '+998901234567',
            'password1': 'StrongPass!9842',
            'password2': 'StrongPass!9842',
        })

        self.assertRedirects(response, reverse('profile'))
        self.assertTrue(
            get_user_model().objects.filter(username='sahifa_user').exists()
        )
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_registration_shows_validation_errors(self):
        response = self.client.post(reverse('register'), {
            'username': 'sahifa_user',
            'email': 'user@example.com',
            'password1': 'short',
            'password2': 'different',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'parol', html=False)
        self.assertFalse(
            get_user_model().objects.filter(username='sahifa_user').exists()
        )

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse('profile'))

        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("profile")}',
        )

    def test_login_preserves_safe_chat_destination(self):
        get_user_model().objects.create_user(
            username='chat_login_user',
            email='chat-login@example.com',
            password='StrongPass!9842',
        )
        next_url = '/messages/'

        login_page = self.client.get(
            reverse('login'),
            {'next': next_url},
        )
        self.assertContains(login_page, 'name="next" value="/messages/"')
        response = self.client.post(
            f'{reverse("login")}?next={next_url}',
            {
                'username': 'chat_login_user',
                'password': 'StrongPass!9842',
                'next': next_url,
            },
        )

        self.assertRedirects(response, next_url, fetch_redirect_response=False)

    def test_profile_shows_user_details_and_default_avatar(self):
        user = get_user_model().objects.create_user(
            username='profile_user',
            email='profile@example.com',
            password='StrongPass!9842',
            phone_number='+998901234567',
            bio='Blog yozishni yaxshi ko‘raman.',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('profile'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'profile@example.com')
        self.assertContains(response, '+998901234567')
        self.assertContains(response, 'Blog yozishni yaxshi ko‘raman.')
        self.assertEqual(
            response.context['profile_avatar'],
            '/static/images/avatar-default.svg',
        )

    def test_profile_links_to_separate_post_creation_page(self):
        user = get_user_model().objects.create_user(
            username='profile_post_link',
            email='profile-post-link@example.com',
            password='StrongPass!9842',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('profile'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('post_create'))
        self.assertContains(response, 'Post qo‘shish')
        self.assertNotContains(response, 'name="title"')

    def test_profile_uses_google_avatar_when_no_uploaded_avatar_exists(self):
        user = get_user_model().objects.create_user(
            username='google_user',
            email='google@example.com',
            password='StrongPass!9842',
        )
        SocialAccount.objects.create(
            user=user,
            provider='google',
            uid='google-user-123',
            extra_data={'picture': 'https://lh3.googleusercontent.com/avatar.jpg'},
        )
        self.client.force_login(user)

        response = self.client.get(reverse('profile'))

        self.assertEqual(
            response.context['profile_avatar'],
            'https://lh3.googleusercontent.com/avatar.jpg',
        )


class ProfileEditingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='edit_user',
            email='before@example.com',
            password='OldPass!9842',
            phone_number='+998901111111',
            bio='Old bio',
        )
        self.client.force_login(self.user)

    def test_profile_edit_page_renders_separate_forms(self):
        response = self.client.get(reverse('edit_profile'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="form_type" value="profile"')
        self.assertContains(response, 'name="form_type" value="password"')
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_profile_details_update_without_changing_password(self):
        response = self.client.post(reverse('edit_profile'), {
            'form_type': 'profile',
            'first_name': 'Ali',
            'last_name': 'Valiyev',
            'username': 'updated_user',
            'email': 'after@example.com',
            'phone_number': '+998902222222',
            'bio': 'Updated bio',
        })

        self.assertRedirects(response, reverse('profile'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Ali')
        self.assertEqual(self.user.last_name, 'Valiyev')
        self.assertEqual(self.user.username, 'updated_user')
        self.assertEqual(self.user.email, 'after@example.com')
        self.assertEqual(self.user.phone_number, '+998902222222')
        self.assertEqual(self.user.bio, 'Updated bio')
        self.assertTrue(self.user.check_password('OldPass!9842'))
        self.assertIn('_auth_user_id', self.client.session)

    def test_password_update_without_changing_profile_details(self):
        response = self.client.post(reverse('edit_profile'), {
            'form_type': 'password',
            'old_password': 'OldPass!9842',
            'new_password1': 'NewPass!2764',
            'new_password2': 'NewPass!2764',
        })

        self.assertRedirects(response, reverse('profile'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass!2764'))
        self.assertEqual(self.user.username, 'edit_user')
        self.assertEqual(self.user.email, 'before@example.com')
        self.assertEqual(self.user.bio, 'Old bio')
        self.assertIn('_auth_user_id', self.client.session)

    def test_google_user_can_set_a_password_without_current_password(self):
        self.client.logout()
        self.user.set_unusable_password()
        self.user.save()
        self.client.force_login(self.user)

        response = self.client.post(reverse('edit_profile'), {
            'form_type': 'password',
            'new_password1': 'NewPass!2764',
            'new_password2': 'NewPass!2764',
        })

        self.assertRedirects(response, reverse('profile'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.has_usable_password())
        self.assertTrue(self.user.check_password('NewPass!2764'))


class ChatPagesTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        media_settings = override_settings(
            MEDIA_ROOT=self.media_directory.name,
            PRIVATE_CHAT_MEDIA_ROOT=self.media_directory.name,
        )
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.user = get_user_model().objects.create_user(
            username='chat_user',
            email='chat@example.com',
            password='StrongPass!9842',
        )
        self.peer = get_user_model().objects.create_user(
            username='chat_peer',
            email='peer@example.com',
            password='StrongPass!9842',
        )

    def test_chat_inbox_is_available_at_correct_messages_url(self):
        self.client.force_login(self.user)

        response = self.client.get('/messages/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Xabarlaringiz')
        self.assertEqual(reverse('chat_inbox'), '/messages/')
        self.assertEqual(reverse('chat_inbox_legacy'), '/messsages/')

    def test_public_profile_has_chat_button_for_other_users(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('public_profile', args=[self.peer.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse('start_chat', args=[self.peer.pk]),
        )
        self.assertContains(response, 'Chat')

    def test_start_chat_creates_conversation_and_opens_chat(self):
        from .models import Conversation, DirectMessage

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('start_chat', args=[self.peer.pk]),
        )

        self.assertEqual(response.status_code, 302)
        conversation = Conversation.objects.get()
        self.assertRedirects(
            response,
            reverse('chat_conversation', args=[conversation.pk]),
        )
        DirectMessage.objects.create(
            conversation=conversation,
            sender=self.user,
            text='O‘zim yuborgan xabar',
        )
        chat_response = self.client.get(response.url)
        self.assertEqual(chat_response.status_code, 200)
        self.assertContains(chat_response, 'data-message-action="edit"')
        self.assertContains(chat_response, 'data-message-action="delete"')
        self.assertContains(chat_response, 'data-message-type="text"')

    def test_chat_requires_login_and_conversation_participation(self):
        from .models import Conversation

        conversation = Conversation.objects.create(
            participant_a=self.user,
            participant_b=self.peer,
        )
        response = self.client.get(
            reverse('chat_conversation', args=[conversation.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            f'{reverse("login")}?next={reverse("chat_conversation", args=[conversation.pk])}',
        )

        outsider = get_user_model().objects.create_user(
            username='chat_outsider',
            email='outsider@example.com',
            password='StrongPass!9842',
        )
        self.client.force_login(outsider)
        response = self.client.get(
            reverse('chat_conversation', args=[conversation.pk]),
        )
        self.assertRedirects(response, reverse('chat_inbox'))

    def test_chat_image_upload_saves_and_broadcasts_media(self):
        from io import BytesIO
        from PIL import Image
        from .models import Conversation, DirectMessage

        conversation = Conversation.objects.create(
            participant_a=self.user,
            participant_b=self.peer,
        )
        self.client.force_login(self.user)
        image_buffer = BytesIO()
        Image.new('RGB', (1, 1), color='green').save(image_buffer, format='PNG')
        image_content = image_buffer.getvalue()

        response = self.client.post(
            reverse('chat_media_upload', args=[conversation.pk]),
            {
                'type': 'image',
                'file': SimpleUploadedFile(
                    'picture.png',
                    image_content,
                    content_type='image/png',
                ),
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['message']['message_type'], 'image')
        self.assertEqual(
            response.json()['message']['media_url'],
            reverse('chat_media_file', args=[response.json()['message']['id'], 'image']),
        )
        message = DirectMessage.objects.get()
        self.assertEqual(message.sender, self.user)
        self.assertTrue(message.image)

        media_response = self.client.get(
            response.json()['message']['media_url'],
        )
        self.assertEqual(media_response.status_code, 200)
        self.assertEqual(media_response['Content-Type'], 'image/png')
        self.assertEqual(b''.join(media_response.streaming_content), image_content)

    def test_chat_media_upload_rejects_non_participants(self):
        from .models import Conversation

        conversation = Conversation.objects.create(
            participant_a=self.user,
            participant_b=self.peer,
        )
        outsider = get_user_model().objects.create_user(
            username='upload_outsider',
            email='upload-outsider@example.com',
            password='StrongPass!9842',
        )
        self.client.force_login(outsider)

        response = self.client.post(
            reverse('chat_media_upload', args=[conversation.pk]),
            {'type': 'image'},
        )

        self.assertEqual(response.status_code, 403)

    def test_chat_audio_upload_creates_audio_message(self):
        from .models import Conversation, DirectMessage

        conversation = Conversation.objects.create(
            participant_a=self.user,
            participant_b=self.peer,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('chat_media_upload', args=[conversation.pk]),
            {
                'type': 'audio',
                'file': SimpleUploadedFile(
                    'voice.webm',
                    b'\x1a\x45\xdf\xa3voice-data',
                    content_type='audio/webm;codecs=opus',
                ),
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['message']['message_type'], 'audio')
        self.assertTrue(DirectMessage.objects.get().audio)

    def test_chat_media_files_are_hidden_from_non_participants(self):
        from .models import Conversation, DirectMessage

        conversation = Conversation.objects.create(
            participant_a=self.user,
            participant_b=self.peer,
        )
        message = DirectMessage.objects.create(
            conversation=conversation,
            sender=self.user,
            message_type='image',
            image=SimpleUploadedFile(
                'hidden.png',
                b'\x89PNG\r\n\x1a\n',
                content_type='image/png',
            ),
        )
        outsider = get_user_model().objects.create_user(
            username='media_outsider',
            email='media-outsider@example.com',
            password='StrongPass!9842',
        )
        self.client.force_login(outsider)

        response = self.client.get(
            reverse('chat_media_file', args=[message.pk, 'image']),
        )

        self.assertEqual(response.status_code, 404)


@override_settings(ALLOWED_HOSTS=['testserver'])
class ChatWebSocketTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='socket_user',
            email='socket@example.com',
            password='StrongPass!9842',
        )
        self.peer = get_user_model().objects.create_user(
            username='socket_peer',
            email='socket-peer@example.com',
            password='StrongPass!9842',
        )
        from .models import Conversation

        self.conversation = Conversation.objects.create(
            participant_a=self.user,
            participant_b=self.peer,
        )

    async def test_authenticated_participants_exchange_messages_live(self):
        from asgiref.sync import sync_to_async
        from channels.testing import WebsocketCommunicator
        from django.conf import settings
        from config.asgi import application
        from .models import DirectMessage

        first_client = self.client
        second_client = self.client_class()
        await sync_to_async(first_client.force_login)(self.user)
        await sync_to_async(second_client.force_login)(self.peer)
        first_session = await sync_to_async(
            lambda: first_client.session.session_key,
        )()
        second_session = await sync_to_async(
            lambda: second_client.session.session_key,
        )()
        path = f'/ws/chat/{self.conversation.pk}/'

        def communicator(session_key):
            return WebsocketCommunicator(
                application,
                path,
                headers=[
                    (
                        b'cookie',
                        f'{settings.SESSION_COOKIE_NAME}={session_key}'.encode(),
                    ),
                    (b'origin', b'http://testserver'),
                ],
            )

        first = communicator(first_session)
        connected, _ = await first.connect()
        self.assertTrue(connected)
        self.assertEqual((await first.receive_json_from())['type'], 'presence')

        second = communicator(second_session)
        connected, _ = await second.connect()
        self.assertTrue(connected)
        second_presence = await second.receive_json_from()
        self.assertTrue(second_presence['online'])
        first_presence = await first.receive_json_from()
        self.assertTrue(first_presence['online'])

        await first.send_json_to({'type': 'typing', 'typing': True})
        self.assertEqual(
            await second.receive_json_from(),
            {'type': 'typing', 'typing': True},
        )
        await first.send_json_to({'type': 'message', 'text': 'Salom, real-time!'})
        first_message = await first.receive_json_from()
        second_message = await second.receive_json_from()
        self.assertEqual(first_message['type'], 'message')
        self.assertEqual(
            first_message['message']['text'],
            'Salom, real-time!',
        )
        self.assertEqual(second_message, first_message)
        self.assertEqual(
            await sync_to_async(DirectMessage.objects.count)(),
            1,
        )
        self.assertTrue(
            await sync_to_async(
                lambda: DirectMessage.objects.get().is_read,
            )(),
        )
        message_id = first_message['message']['id']

        await second.send_json_to({
            'type': 'edit_message',
            'message_id': message_id,
            'text': 'Ruxsatsiz tahrir',
        })
        self.assertEqual(
            (await second.receive_json_from())['type'],
            'error',
        )
        await second.send_json_to({
            'type': 'delete_message',
            'message_id': message_id,
        })
        self.assertEqual(
            (await second.receive_json_from())['type'],
            'error',
        )
        self.assertEqual(
            await sync_to_async(
                lambda: DirectMessage.objects.get().text,
            )(),
            'Salom, real-time!',
        )

        await first.send_json_to({
            'type': 'edit_message',
            'message_id': message_id,
            'text': 'Tahrirlangan xabar',
        })
        first_update = await first.receive_json_from()
        second_update = await second.receive_json_from()
        self.assertEqual(first_update['type'], 'message_updated')
        self.assertEqual(second_update, first_update)
        self.assertEqual(
            first_update['message']['text'],
            'Tahrirlangan xabar',
        )
        self.assertTrue(
            await sync_to_async(
                lambda: DirectMessage.objects.get().edited_at is not None,
            )(),
        )

        await first.send_json_to({
            'type': 'delete_message',
            'message_id': message_id,
        })
        first_delete = await first.receive_json_from()
        second_delete = await second.receive_json_from()
        self.assertEqual(first_delete['type'], 'message_deleted')
        self.assertEqual(second_delete, first_delete)
        self.assertIsNone(first_delete['last_message'])
        self.assertEqual(
            await sync_to_async(DirectMessage.objects.count)(),
            0,
        )

        await first.disconnect()
        await second.disconnect()

    async def test_deleting_media_message_removes_its_file(self):
        import tempfile

        from asgiref.sync import sync_to_async
        from channels.testing import WebsocketCommunicator
        from django.conf import settings
        from django.test import override_settings
        from config.asgi import application
        from .models import DirectMessage

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(PRIVATE_CHAT_MEDIA_ROOT=media_root):
                message = await sync_to_async(DirectMessage.objects.create)(
                    conversation=self.conversation,
                    sender=self.user,
                    message_type='audio',
                    audio=SimpleUploadedFile(
                        'voice.webm',
                        b'voice-recording',
                        content_type='audio/webm',
                    ),
                )
                file_path = Path(message.audio.path)
                client = self.client
                await sync_to_async(client.force_login)(self.user)
                session_key = await sync_to_async(
                    lambda: client.session.session_key,
                )()
                communicator = WebsocketCommunicator(
                    application,
                    f'/ws/chat/{self.conversation.pk}/',
                    headers=[
                        (
                            b'cookie',
                            f'{settings.SESSION_COOKIE_NAME}={session_key}'.encode(),
                        ),
                        (b'origin', b'http://testserver'),
                    ],
                )

                connected, _ = await communicator.connect()
                self.assertTrue(connected)
                await communicator.receive_json_from()
                await communicator.send_json_to({
                    'type': 'delete_message',
                    'message_id': str(message.pk),
                })
                deleted_event = await communicator.receive_json_from()

                self.assertEqual(deleted_event['type'], 'message_deleted')
                self.assertFalse(
                    await sync_to_async(
                        DirectMessage.objects.filter(pk=message.pk).exists,
                    )(),
                )
                self.assertFalse(file_path.exists())
                await communicator.disconnect()


class HomeAndPostTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='post_author',
            email='author@example.com',
            password='StrongPass!9842',
        )

    def test_home_shows_posts_and_links_to_post_creation(self):
        from .models import Post

        Post.objects.create(
            author=self.user,
            title='Birinchi post',
            desc='Hamjamiyatga salom!',
        )

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Birinchi post')
        self.assertContains(response, 'Hamjamiyatga salom!')
        self.assertContains(response, reverse('login'))
        self.assertNotContains(response, 'name="title"')

    def test_home_search_finds_users_by_username_case_insensitively(self):
        target = get_user_model().objects.create_user(
            username='SearchTarget',
            email='search-target@example.com',
            password='StrongPass!9842',
        )

        response = self.client.get(reverse('home'), {'q': 'SEARCH'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['user_search_query'], 'SEARCH')
        self.assertEqual(
            [profile.pk for profile in response.context['suggested_users']],
            [target.pk],
        )
        self.assertContains(response, '@SearchTarget')
        self.assertContains(response, 'Qidiruvni tozalash')
        self.assertContains(response, 'id="header-people-search"')
        self.assertNotContains(response, 'id="people-search-input"')

    def test_home_search_finds_users_by_full_name(self):
        target = get_user_model().objects.create_user(
            username='full_name_target',
            email='full-name@example.com',
            password='StrongPass!9842',
            first_name='Aziza',
            last_name='Karimova',
        )

        response = self.client.get(reverse('home'), {'q': 'aziza kar'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [profile.pk for profile in response.context['suggested_users']],
            [target.pk],
        )

    def test_home_search_displays_no_results_message(self):
        response = self.client.get(reverse('home'), {'q': 'no-such-person'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bu so‘rov bo‘yicha foydalanuvchi topilmadi.')
        self.assertEqual(response.context['suggested_users'], [])

    def test_post_create_page_renders_post_form(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('post_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="title"')
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_authenticated_user_creates_post_from_separate_page(self):
        from .models import Post

        self.client.force_login(self.user)
        response = self.client.post(reverse('post_create'), {
            'title': 'Profilimdan post',
            'desc': 'Bu post profile sahifasidan yozildi.',
        }, follow=True)

        self.assertRedirects(response, reverse('profile'))
        self.assertContains(response, 'Profilimdan post')
        post = Post.objects.get(title='Profilimdan post')
        self.assertEqual(post.author, self.user)

    def test_post_create_page_shows_validation_errors(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('post_create'), {
            'title': '',
            'desc': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Post uchun matn, rasm yoki video kiriting.')

    def test_anonymous_user_cannot_open_post_create_page(self):
        response = self.client.get(reverse('post_create'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            f'{reverse("login")}?next={reverse("post_create")}',
        )

    def test_anonymous_user_cannot_create_post_from_post_create_page(self):
        response = self.client.post(reverse('post_create'), {
            'title': 'Ruxsatsiz post',
            'desc': 'Bu post yaratilmasligi kerak.',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            f'{reverse("login")}?next={reverse("post_create")}',
        )

    def test_authenticated_user_can_like_and_unlike_post_with_ajax(self):
        from .models import Post

        post = Post.objects.create(author=self.user, desc='Layk sinovi')
        self.client.force_login(self.user)

        first_response = self.client.post(
            reverse('like_post', args=[post.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        second_response = self.client.post(
            reverse('like_post', args=[post.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json(), {'liked': True, 'likes_count': 1})
        self.assertEqual(second_response.json(), {'liked': False, 'likes_count': 0})

    def test_ajax_comment_is_saved_for_target_post(self):
        from .models import Comment, Post

        post = Post.objects.create(author=self.user, desc='Izoh sinovi')
        commenter = get_user_model().objects.create_user(
            username='commenter',
            email='commenter@example.com',
            password='StrongPass!9842',
        )
        self.client.force_login(commenter)

        response = self.client.post(
            reverse('add_comment', args=[post.pk]),
            {'text': 'Juda yaxshi post!'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['comments_count'], 1)
        comment = Comment.objects.get()
        self.assertEqual(comment.post, post)
        self.assertEqual(comment.author, commenter)
        self.assertEqual(comment.text, 'Juda yaxshi post!')
        self.assertIn('profile_url', response.json()['comment'])

    def test_ajax_follow_and_public_profile(self):
        target = get_user_model().objects.create_user(
            username='follow_target',
            email='follow@example.com',
            password='StrongPass!9842',
        )
        self.client.force_login(self.user)

        follow_response = self.client.post(
            reverse('follow_toggle', args=[target.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        profile_response = self.client.get(
            reverse('public_profile', args=[target.pk])
        )

        self.assertEqual(
            follow_response.json(),
            {'following': True, 'followers_count': 1},
        )
        self.assertEqual(profile_response.status_code, 200)
        self.assertContains(profile_response, '@follow_target')
        self.assertContains(profile_response, 'Kuzatyapsiz')

    def test_post_detail_renders_post_and_comments(self):
        from .models import Comment, Post

        post = Post.objects.create(author=self.user, title='Post sahifasi', desc='To‘liq matn')
        Comment.objects.create(post=post, author=self.user, text='Birinchi izoh')

        response = self.client.get(reverse('post_detail', args=[post.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Post sahifasi')
        self.assertContains(response, 'data-comments-toggle')
        self.assertContains(response, 'data-comments-url')
        comments_response = self.client.get(
            reverse('post_comments', args=[post.pk]),
        )
        self.assertEqual(comments_response.status_code, 200)
        self.assertEqual(
            comments_response.json()['comments'][0]['text'],
            'Birinchi izoh',
        )

    def test_ajax_comment_response_includes_profile_and_timestamp(self):
        from .models import Post

        post = Post.objects.create(author=self.user, desc='Izoh metama’lumoti')
        commenter = get_user_model().objects.create_user(
            username='comment_meta',
            email='comment-meta@example.com',
            password='StrongPass!9842',
        )
        self.client.force_login(commenter)

        response = self.client.post(
            reverse('add_comment', args=[post.pk]),
            {'text': 'Izoh avatar bilan'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        comment_data = response.json()['comment']
        self.assertEqual(response.status_code, 200)
        self.assertEqual(comment_data['username'], 'comment_meta')
        self.assertEqual(
            comment_data['avatar_url'],
            '/static/images/avatar-default.svg',
        )
        self.assertTrue(comment_data['created_at'])
        self.assertTrue(comment_data['created_at_iso'])

    def test_ajax_comments_list_includes_author_avatar_and_timestamp(self):
        from .models import Comment, Post

        post = Post.objects.create(author=self.user, desc='Izohlar ro‘yxati')
        Comment.objects.create(
            post=post,
            author=self.user,
            text='Ro‘yxatda ko‘rinadigan izoh',
        )

        response = self.client.get(
            reverse('post_comments', args=[post.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        comment_data = response.json()['comments'][0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(comment_data['username'], 'post_author')
        self.assertEqual(
            comment_data['avatar_url'],
            '/static/images/avatar-default.svg',
        )
        self.assertTrue(comment_data['created_at'])
        self.assertTrue(comment_data['created_at_iso'])

    def test_connection_lists_return_followers_and_following(self):
        target = get_user_model().objects.create_user(
            username='connection_target',
            email='target@example.com',
            password='StrongPass!9842',
        )
        self.user.following.add(target)
        target.following.add(self.user)

        followers_response = self.client.get(reverse(
            'profile_connections',
            args=[target.pk, 'followers'],
        ))
        following_response = self.client.get(reverse(
            'profile_connections',
            args=[self.user.pk, 'following'],
        ))

        self.assertEqual(followers_response.status_code, 200)
        self.assertEqual(
            [person['username'] for person in followers_response.json()['users']],
            ['post_author'],
        )
        self.assertEqual(
            [person['username'] for person in following_response.json()['users']],
            ['connection_target'],
        )
        self.assertIn('avatar_url', followers_response.json()['users'][0])
        self.assertIn('profile_url', following_response.json()['users'][0])

    def test_invalid_connection_type_returns_not_found(self):
        response = self.client.get(reverse(
            'profile_connections',
            args=[self.user.pk, 'unknown'],
        ))

        self.assertEqual(response.status_code, 404)

    def test_empty_post_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('post_create'), {
            'title': '',
            'desc': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Post uchun matn, rasm yoki video kiriting.')
