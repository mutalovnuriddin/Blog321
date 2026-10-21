from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib import messages
from django.core.cache import cache

from django.http import JsonResponse
from django.http import FileResponse, Http404
from django.core.files.uploadedfile import UploadedFile
from django.core.exceptions import ValidationError
from django.forms import ImageField
from django.utils import timezone
from django.urls import reverse
from django.templatetags.static import static
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import BooleanField, CharField, Count, Exists, OuterRef, Prefetch, Value, Q
from django.db.models.functions import Concat
from allauth.socialaccount.models import SocialAccount
from .forms import (
    ProfileCreateForm,
    ProfileLoginForm,
    ProfilePasswordChangeForm,
    ProfileSetPasswordForm,
    ProfileUpdateForm,
    PostCreatedForm,
    CommentForm
)
from .models import Comment, Post, Profile, Conversation, DirectMessage, Notification
from .notifications import (
    create_notification,
    notify_group_name,
    serialize_notification,
)

# Create your views here.


def _is_ajax_request(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _redirect_after_action(request):
    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(reverse('home'))

def _avatar_urls(user, google_account=None):
    avatar = user.avatar
    default_avatar = user._meta.get_field('avatar').get_default()
    local_avatar_url = (
        avatar.url
        if avatar and avatar.name != default_avatar
        else None
    )
    google_avatar_url = (
        google_account.extra_data.get('picture')
        if google_account and google_account.extra_data
        else None
    )
    if google_avatar_url and not google_avatar_url.startswith('https://'):
        google_avatar_url = None
    if not google_avatar_url and local_avatar_url:
        google_avatar_url = local_avatar_url
    return local_avatar_url, google_avatar_url


def _avatar_url_for_user(user, google_account=None):
    if google_account is None:
        google_account = SocialAccount.objects.filter(
            user=user,
            provider='google',
        ).first()
    local_avatar_url, google_avatar_url = _avatar_urls(user, google_account)
    return local_avatar_url or google_avatar_url or static('images/avatar-default.svg')


def _posts_for_user(request, queryset):
    likes_field = Post._meta.get_field('likes')
    through = likes_field.remote_field.through
    post_field = likes_field.m2m_reverse_field_name()
    user_field = likes_field.m2m_field_name()
    posts = list(queryset.annotate(
        likes_count=Count('likes', distinct=True),
        comments_count=Count('comments', distinct=True),
        is_liked=Exists(through.objects.filter(
            **{
                f'{post_field}_id': OuterRef('pk'),
                f'{user_field}_id': request.user.pk,
            }
        )) if request.user.is_authenticated else Value(
            False,
            output_field=BooleanField(),
        ),
    ).prefetch_related(
        Prefetch(
            'comments',
            queryset=Comment.objects.select_related('author'),
        ),
    ))
    profile_ids = {post.author_id for post in posts}
    comment_authors = []
    for post in posts:
        comment_authors.extend(comment.author for comment in post.comments.all())
    profile_ids.update(comment.pk for comment in comment_authors)
    google_accounts = {
        account.user_id: account
        for account in SocialAccount.objects.filter(
            user_id__in=profile_ids,
            provider='google',
        )
    }

    for post in posts:
        post.author_avatar = _avatar_url_for_user(
            post.author,
            google_accounts.get(post.author_id),
        )
        for comment in post.comments.all():
            comment.author_avatar = _avatar_url_for_user(
                comment.author,
                google_accounts.get(comment.author_id),
            )
    return posts


def _profile_context(request, profile):
    is_following = (
        request.user.is_authenticated
        and request.user.following.filter(pk=profile.pk).exists()
    )
    return {
        'profile_user': profile,
        'profile_avatar': _avatar_url_for_user(profile),
        'user_posts': _posts_for_user(
            request,
            Post.objects.filter(author=profile).select_related('author'),
        ),
        'posts_count': Post.objects.filter(author=profile).count(),
        'followers_count': Profile.objects.filter(following=profile).count(),
        'following_count': profile.following.count(),
        'is_following': is_following,
        'is_online': cache.get(f"chat:presence:{profile.pk}", 0) > 0,
    }


def _suggested_profiles(request, limit=5):
    profiles = Profile.objects.all()
    if request.user.is_authenticated:
        profiles = profiles.exclude(pk=request.user.pk).exclude(
            pk__in=request.user.following.values('pk'),
        )
    profiles = list(profiles.order_by('-date_joined')[:limit])
    google_accounts = {
        account.user_id: account
        for account in SocialAccount.objects.filter(
            user_id__in=[profile.pk for profile in profiles],
            provider='google',
        )
    }
    for profile in profiles:
        profile.avatar_url = _avatar_url_for_user(
            profile,
            google_accounts.get(profile.pk),
        )
    return profiles


def _search_profiles(request, query, limit=30):
    profiles = list(
        Profile.objects.annotate(
            full_name=Concat(
                'first_name',
                Value(' '),
                'last_name',
                output_field=CharField(),
            ),
        ).filter(
            Q(username__icontains=query)
            | Q(full_name__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        ).order_by('username')[:limit]
    )
    google_accounts = {
        account.user_id: account
        for account in SocialAccount.objects.filter(
            user_id__in=[profile.pk for profile in profiles],
            provider='google',
        )
    }
    for profile in profiles:
        profile.avatar_url = _avatar_url_for_user(
            profile,
            google_accounts.get(profile.pk),
        )
        profile.is_following = (
            request.user.is_authenticated
            and request.user.following.filter(pk=profile.pk).exists()
        )
    return profiles


def _conversation_for_users(first_user, second_user):
    participant_a, participant_b = sorted(
        (first_user, second_user),
        key=lambda user: str(user.pk),
    )
    conversation, _ = Conversation.objects.get_or_create(
        participant_a=participant_a,
        participant_b=participant_b,
    )
    return conversation


def _chat_sidebar(user, active_conversation=None):
    conversations = list(
        Conversation.objects.filter(
            Q(participant_a=user) | Q(participant_b=user)
        )
        .select_related('participant_a', 'participant_b')
        .annotate(
            unread_count=Count(
                'messages',
                filter=Q(messages__is_read=False)
                & ~Q(messages__sender_id=user.pk),
            )
        )
        .prefetch_related(Prefetch(
            'messages',
            queryset=DirectMessage.objects.order_by('-created_at')[:1],
            to_attr='latest_messages',
        ))
        .order_by('-updated_at')
    )
    peers = [
        conversation.participant_for(user)
        for conversation in conversations
    ]
    peer_ids = {peer.pk for peer in peers}
    google_accounts = {
        account.user_id: account
        for account in SocialAccount.objects.filter(
            user_id__in=peer_ids,
            provider='google',
        )
    }
    items = []
    for conversation, peer in zip(conversations, peers):
        local_avatar_url, google_avatar_url = _avatar_urls(
            peer,
            google_accounts.get(peer.pk),
        )
        latest_message = (
            conversation.latest_messages[0]
            if conversation.latest_messages
            else None
        )
        items.append({
            'conversation': conversation,
            'peer': peer,
            'peer_avatar_url': local_avatar_url or google_avatar_url,
            'conversation_url': reverse(
                'chat_conversation',
                args=[conversation.pk],
            ),
            'is_active': (
                active_conversation is not None
                and conversation.pk == active_conversation.pk
            ),
            'is_online': cache.get(f"chat:presence:{peer.pk}", 0) > 0,
            'last_message': latest_message,
            'unread_count': conversation.unread_count,
        })
    return items


def register_page(request):
    if request.user.is_authenticated:
        return redirect('profile')
    if request.method == 'POST':
        form = ProfileCreateForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('profile')
    else:
        form = ProfileCreateForm()
    return render(request, 'register.html', {'form': form})



def login_page(request):
    if request.user.is_authenticated:
        return redirect('profile')
    if request.method == 'POST':
        form = ProfileLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next', '')
            if url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect('profile')
    else:
        form = ProfileLoginForm()
    return render(request, 'login.html', {'form': form})



@login_required
def profile_page(request):
    user = request.user
    context = _profile_context(request, user)
    context['suggested_users'] = _suggested_profiles(request)
    return render(request, 'profile.html', context)


@login_required
def post_create_view(request):
    post_form = PostCreatedForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
    )
    if request.method == 'POST' and post_form.is_valid():
        post = post_form.save(commit=False)
        post.author = request.user
        post.save()
        messages.success(request, 'Postingiz muvaffaqiyatli joylandi.')
        return redirect('profile')

    return render(request, 'post_create.html', {
        'post_form': post_form,
        'post_form_title': 'Yangi post',
        'post_form_intro': 'Fikringiz, rasm yoki videongizni ulashing.',
        'post_form_action': 'Postni ulashish',
        'post_form_back_url': reverse('profile'),
        'post_form_back_label': 'Profilga qaytish',
    })


@login_required
def post_update_view(request, post_id):
    post = get_object_or_404(Post, pk=post_id, author=request.user)
    post_form = PostCreatedForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
        instance=post,
    )
    if request.method == 'POST' and post_form.is_valid():
        post_form.save()
        messages.success(request, 'Postingiz yangilandi.')
        return redirect('post_detail', post_id=post.pk)

    return render(request, 'post_create.html', {
        'post_form': post_form,
        'post_form_title': 'Postni tahrirlash',
        'post_form_intro': 'Post matni va media fayllarini yangilang.',
        'post_form_action': 'O‘zgarishlarni saqlash',
        'post_form_back_url': reverse('post_detail', args=[post.pk]),
        'post_form_back_label': 'Postga qaytish',
    })


@login_required
@require_POST
def post_delete_view(request, post_id):
    post = get_object_or_404(Post, pk=post_id, author=request.user)
    post.delete()
    return redirect('home')


@require_POST
def logout_page(request):
    logout(request)
    return redirect('login')


@login_required
def profile_edit_view(request):
    profile_form = ProfileUpdateForm(instance=request.user)
    password_form_class = (
        ProfilePasswordChangeForm
        if request.user.has_usable_password()
        else ProfileSetPasswordForm
    )
    password_form = password_form_class(request.user)

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'profile':
            profile_form = ProfileUpdateForm(
                request.POST,
                request.FILES,
                instance=request.user
            )

            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profil ma’lumotlaringiz yangilandi.')
                return redirect('profile')

        elif form_type == 'password':
            password_form = password_form_class(request.user, request.POST)

            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Parolingiz muvaffaqiyatli yangilandi.')
                return redirect('profile')

    context = {
        'profile_form': profile_form,
        'password_form': password_form,
        'password_form_title': (
            'Parol o‘rnatish'
            if not request.user.has_usable_password()
            else 'Parolni o‘zgartirish'
        ),
    }

    return render(request, 'profile_edit.html', context)


def home_page(request):
    queryset = Post.objects.select_related('author').all()
    posts = _posts_for_user(request, queryset)
    search_query = request.GET.get('q', '').strip()[:100]
    suggested_users = (
        _search_profiles(request, search_query)
        if search_query
        else _suggested_profiles(request)
    )
    return render(request, 'index.html', {
        'posts': posts,
        'suggested_users': suggested_users,
        'user_search_query': search_query,
        'user_search_active': bool(search_query),
    })


def public_profile_page(request, user_id):
    profile = get_object_or_404(Profile, pk=user_id)
    context = _profile_context(request, profile)
    context['is_own_profile'] = request.user.is_authenticated and request.user.pk == profile.pk
    return render(request, 'public_profile.html', context)


def post_detail_page(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    posts = _posts_for_user(
        request,
        Post.objects.filter(pk=post.pk).select_related('author'),
    )
    prepared_post = posts[0]
    return render(request, 'post_detail.html', {
        'post': prepared_post,
        'post_detail': True,
    })



@login_required
@require_POST
def like_post_page(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if post.likes.filter(pk=request.user.pk).exists():
        post.likes.remove(request.user)
        is_liked = False
        Notification.objects.filter(
            recipient=post.author,
            actor=request.user,
            verb=Notification.Verb.LIKE,
            post=post,
        ).delete()
    else:
        post.likes.add(request.user)
        is_liked = True
        create_notification(
            recipient=post.author,
            actor=request.user,
            verb='like',
            post=post,
        )
    if _is_ajax_request(request):
        return JsonResponse({
            'liked': is_liked,
            'likes_count': post.likes.count(),
        })
    return _redirect_after_action(request)



@login_required
@require_POST
def add_comment_page(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.author = request.user
        comment.post = post
        comment.save()
        create_notification(
            recipient=post.author,
            actor=request.user,
            verb='comment',
            post=post,
            comment=comment,
            preview=comment.text,
        )
        if _is_ajax_request(request):
            return JsonResponse({
                'comment': {
                    'id': str(comment.pk),
                    'text': comment.text,
                    'username': request.user.username,
                    'display_name': request.user.get_full_name() or request.user.username,
                    'profile_url': reverse('public_profile', args=[request.user.pk]),
                    'avatar_url': _avatar_url_for_user(request.user),
                    'created_at': timezone.localtime(comment.created_at).strftime(
                        '%d.%m.%Y · %H:%M'
                    ),
                    'created_at_iso': comment.created_at.isoformat(),
                    'time_ago': 'hozir',
                },
                'comments_count': post.comments.count(),
            })
    else:
        if _is_ajax_request(request):
            return JsonResponse({
                'errors': form.errors.get_json_data(),
            }, status=400)
        messages.error(request, 'Izoh yuborishdan oldin matn kiriting.')
    return _redirect_after_action(request)


def post_comments_page(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    comments = list(
        post.comments.select_related('author').order_by('created_at')
    )
    author_ids = {comment.author_id for comment in comments}
    google_accounts = {
        account.user_id: account
        for account in SocialAccount.objects.filter(
            user_id__in=author_ids,
            provider='google',
        )
    }
    return JsonResponse({
        'comments': [
            {
                'id': str(comment.pk),
                'text': comment.text,
                'username': comment.author.username,
                'display_name': comment.author.get_full_name() or comment.author.username,
                'profile_url': reverse('public_profile', args=[comment.author.pk]),
                'avatar_url': _avatar_url_for_user(
                    comment.author,
                    google_accounts.get(comment.author_id),
                ),
                'created_at': timezone.localtime(comment.created_at).strftime(
                    '%d.%m.%Y · %H:%M'
                ),
                'created_at_iso': comment.created_at.isoformat(),
            }
            for comment in comments
        ],
        'comments_count': len(comments),
    })


def profile_connections_page(request, user_id, connection_type):
    profile = get_object_or_404(Profile, pk=user_id)
    if connection_type == 'followers':
        users = Profile.objects.filter(following=profile)
    elif connection_type == 'following':
        users = profile.following.all()
    else:
        return JsonResponse({'error': 'Noma’lum ro‘yxat turi.'}, status=404)

    users = list(users.order_by('username'))
    google_accounts = {
        account.user_id: account
        for account in SocialAccount.objects.filter(
            user_id__in=[user.pk for user in users],
            provider='google',
        )
    }
    return JsonResponse({
        'users': [
            {
                'username': user.username,
                'display_name': user.get_full_name() or user.username,
                'profile_url': reverse('public_profile', args=[user.pk]),
                'avatar_url': _avatar_url_for_user(
                    user,
                    google_accounts.get(user.pk),
                ),
            }
            for user in users
        ],
        'count': len(users),
    })



@login_required
@require_POST
def follow_toggle_page(request, user_id):
    target_user = get_object_or_404(Profile, pk=user_id)
    if target_user != request.user:
        if request.user.following.filter(id=target_user.id).exists():
            request.user.following.remove(target_user)
            is_following = False
        else:
            request.user.following.add(target_user)
            is_following = True
            create_notification(
                recipient=target_user,
                actor=request.user,
                verb='follow',
            )
    else:
        is_following = False

    if _is_ajax_request(request):
        return JsonResponse({
            'following': is_following,
            'followers_count': Profile.objects.filter(following=target_user).count(),
        })
    return _redirect_after_action(request)


@login_required
def notifications_data_page(request):
    """🔔 Dropdown uchun oxirgi bildirishnomalar va o'qilmaganlar soni."""
    notifications = list(
        request.user.received_notifications.select_related(
            'actor',
            'post',
            'conversation',
        )[:30]
    )
    return JsonResponse({
        'unread_count': request.user.received_notifications.filter(
            is_read=False,
        ).count(),
        'notifications': [
            serialize_notification(notification)
            for notification in notifications
        ],
    })


@login_required
@require_POST
def notifications_read_page(request):
    """Bildirishnomalarni o'qilgan deb belgilaydi:
    id yuborilsa — bittasini, aks holda hammasini."""
    notification_id = request.POST.get('id', '').strip()
    queryset = request.user.received_notifications.filter(is_read=False)
    if notification_id:
        queryset = queryset.filter(pk=notification_id)
    queryset.update(is_read=True)

    unread_count = request.user.received_notifications.filter(
        is_read=False,
    ).count()

    channel_layer = get_channel_layer()
    if channel_layer is not None:
        async_to_sync(channel_layer.group_send)(
            notify_group_name(request.user.pk),
            {
                'type': 'unread_count_refreshed',
                'count': unread_count,
            },
        )
    return JsonResponse({'unread_count': unread_count})


@login_required
def notifications_data_page(request):
    """🔔 Dropdown uchun oxirgi bildirishnomalar va o'qilmaganlar soni."""
    notifications = list(
        request.user.received_notifications.select_related(
            'actor',
            'post',
            'conversation',
        )[:30]
    )
    return JsonResponse({
        'unread_count': request.user.received_notifications.filter(
            is_read=False,
        ).count(),
        'notifications': [
            serialize_notification(notification)
            for notification in notifications
        ],
    })


@login_required
@require_POST
def notifications_read_page(request):
    """Bildirishnomalarni o'qilgan deb belgilaydi:
    id yuborilsa — bittasini, aks holda hammasini."""
    notification_id = request.POST.get('id', '').strip()
    queryset = request.user.received_notifications.filter(is_read=False)
    if notification_id:
        queryset = queryset.filter(pk=notification_id)
    queryset.update(is_read=True)

    unread_count = request.user.received_notifications.filter(
        is_read=False,
    ).count()

    channel_layer = get_channel_layer()
    if channel_layer is not None:
        async_to_sync(channel_layer.group_send)(
            notify_group_name(request.user.pk),
            {
                'type': 'unread_count_refreshed',
                'count': unread_count,
            },
        )
    return JsonResponse({'unread_count': unread_count})


@login_required
def start_chat_page(request, user_id):
    target_user = get_object_or_404(Profile, pk=user_id)
    if target_user.pk == request.user.pk:
        return redirect('chat_inbox')
    conversation = _conversation_for_users(request.user, target_user)
    return redirect('chat_conversation', conversation_id=conversation.pk)


@login_required
def chat_inbox_page(request):
    return render(request, 'chat.html', {
        'chat_items': _chat_sidebar(request.user),
        'active_conversation': None,
        'peer': None,
        'peer_avatar_url': None,
        'messages': [],
        'is_peer_online': False,
        'chat_socket_path': '',
    })


@login_required
def chat_conversation_page(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.select_related('participant_a', 'participant_b'),
        pk=conversation_id,
    )
    peer = conversation.participant_for(request.user)
    if peer is None:
        return redirect('chat_inbox')

    conversation.messages.filter(
        is_read=False,
    ).exclude(sender=request.user).update(is_read=True)
    peer_avatar_url = _avatar_url_for_user(peer)
    chat_messages = list(
        conversation.messages.select_related('sender')
        .order_by('-created_at')[:100]
    )
    chat_messages.reverse()
    return render(request, 'chat.html', {
        'chat_items': _chat_sidebar(request.user, conversation),
        'active_conversation': conversation,
        'peer': peer,
        'peer_avatar_url': peer_avatar_url,
        'messages': chat_messages,
        'is_peer_online': cache.get(f"chat:presence:{peer.pk}", 0) > 0,
        'chat_socket_path': f'/ws/chat/{conversation.pk}/',
        'chat_upload_url': reverse('chat_media_upload', args=[conversation.pk]),
    })


@login_required
@require_POST
def chat_media_upload_page(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.select_related('participant_a', 'participant_b'),
        pk=conversation_id,
    )
    if conversation.participant_for(request.user) is None:
        return JsonResponse({'error': 'Bu suhbatga ruxsatingiz yo‘q.'}, status=403)

    upload_type = request.POST.get('type')
    upload = request.FILES.get('file')
    if not isinstance(upload, UploadedFile):
        return JsonResponse({'error': 'Yuklanadigan fayl topilmadi.'}, status=400)

    if upload_type == DirectMessage.MessageType.IMAGE:
        if upload.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'Rasm 10 MB dan kichik bo‘lishi kerak.'}, status=400)
        try:
            ImageField().clean(upload)
        except ValidationError:
            return JsonResponse({'error': 'Yaroqli rasm faylini tanlang.'}, status=400)
        if not upload.content_type or not upload.content_type.startswith('image/'):
            return JsonResponse({'error': 'Faqat rasm yuborish mumkin.'}, status=400)
    elif upload_type == DirectMessage.MessageType.AUDIO:
        allowed_audio_types = {
            'audio/webm': {'webm'},
            'audio/ogg': {'ogg', 'oga'},
            'audio/mp4': {'m4a', 'mp4'},
            'audio/mpeg': {'mp3'},
            'audio/wav': {'wav'},
            'audio/x-wav': {'wav'},
        }
        if upload.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'Ovozli xabar 10 MB dan kichik bo‘lishi kerak.'}, status=400)
        audio_type = upload.content_type.split(';', 1)[0].strip()
        extension = upload.name.rsplit('.', 1)[-1].lower()
        if extension not in allowed_audio_types.get(audio_type, set()):
            return JsonResponse({'error': 'Brauzer yozgan audio formatini yuboring.'}, status=400)
    else:
        return JsonResponse({'error': 'Fayl turi noto‘g‘ri.'}, status=400)

    message = DirectMessage(
        conversation=conversation,
        sender=request.user,
        message_type=upload_type,
        text='',
    )
    if upload_type == DirectMessage.MessageType.IMAGE:
        message.image = upload
    else:
        message.audio = upload
    message.save()
    Conversation.objects.filter(pk=conversation.pk).update(
        updated_at=message.created_at,
    )

    avatar_url = _avatar_url_for_user(request.user)
    media_url = reverse(
        'chat_media_file',
        args=[message.pk, upload_type],
    )
    serialized_message = {
        'id': str(message.pk),
        'text': message.text,
        'message_type': message.message_type,
        'media_url': media_url,
        'sender_id': str(request.user.pk),
        'sender_name': request.user.get_full_name() or request.user.username,
        'avatar_url': avatar_url,
        'created_at': timezone.localtime(message.created_at).strftime('%H:%M'),
        'created_at_iso': message.created_at.isoformat(),
    }
    async_to_sync(get_channel_layer().group_send)(
        f'chat_{conversation.pk.hex}',
        {
            'type': 'message_created',
            'message': serialized_message,
        },
    )
    return JsonResponse({'message': serialized_message}, status=201)


@login_required
def chat_media_file_page(request, message_id, media_type):
    message = get_object_or_404(
        DirectMessage.objects.select_related(
            'conversation__participant_a',
            'conversation__participant_b',
        ),
        pk=message_id,
    )
    if message.conversation.participant_for(request.user) is None:
        raise Http404

    if media_type == DirectMessage.MessageType.IMAGE:
        uploaded_file = message.image
        content_type = 'image'
    elif media_type == DirectMessage.MessageType.AUDIO:
        uploaded_file = message.audio
        content_type = 'audio'
    else:
        raise Http404
    if not uploaded_file:
        raise Http404

    extension = uploaded_file.name.rsplit('.', 1)[-1].lower()
    mime_types = {
        'webm': 'audio/webm',
        'ogg': 'audio/ogg',
        'mp3': 'audio/mpeg',
        'wav': 'audio/wav',
        'm4a': 'audio/mp4',
    }
    if content_type == 'audio':
        response_type = mime_types.get(extension, 'application/octet-stream')
    else:
        response_type = f'image/{extension}' if extension in {
            'png',
            'jpeg',
            'jpg',
            'gif',
            'webp',
            'bmp',
        } else 'application/octet-stream'

    response = FileResponse(
        uploaded_file.open('rb'),
        content_type=response_type,
        filename=uploaded_file.name.rsplit('/', 1)[-1],
    )
    response['X-Content-Type-Options'] = 'nosniff'
    return response