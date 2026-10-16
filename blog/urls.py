from django.urls import path
from .views import (
    add_comment_page,
    follow_toggle_page,
    home_page,
    like_post_page,
    login_page,
    logout_page,
    post_detail_page,
    post_comments_page,
    post_create_view,
    post_delete_view,
    post_update_view,
    profile_connections_page,
    profile_edit_view,
    profile_page,
    public_profile_page,
    register_page,
    start_chat_page, 
    chat_conversation_page, 
    chat_inbox_page,
    chat_media_upload_page,
    chat_media_file_page,
)



urlpatterns = [
    path('', home_page, name='home'),
    path('login/', login_page, name='login'),
    path('register/', register_page, name='register'),
    path('profile/', profile_page, name='profile'),
    path('logout/', logout_page, name='logout'),
    path('profile/update/', profile_edit_view, name='edit_profile'),
    path('post/<uuid:post_id>/', post_detail_page, name='post_detail'),
    path('post/create/', post_create_view, name='post_create'),
    path('post/<uuid:post_id>/edit/', post_update_view, name='post_update'),
    path('post/<uuid:post_id>/delete/', post_delete_view, name='post_delete'),
    path('post/<uuid:post_id>/comments/', post_comments_page, name='post_comments'),
    path('post/<uuid:post_id>/like/', like_post_page, name='like_post'),
    path('post/<uuid:post_id>/comment/', add_comment_page, name='add_comment'),
    path('user/<uuid:user_id>/follow/', follow_toggle_page, name='follow_toggle'),
    path('user/<uuid:user_id>/connections/<str:connection_type>/', profile_connections_page, name='profile_connections'),
    path('user/<uuid:user_id>/', public_profile_page, name='public_profile'),
    path('messages/', chat_inbox_page, name='chat_inbox'),
    path('messsages/', chat_inbox_page, name='chat_inbox_legacy'),
    path('messages/start/<uuid:user_id>/', start_chat_page, name='start_chat'),
    path('messages/<uuid:conversation_id>/', chat_conversation_page, name='chat_conversation'),
    path('messages/media/<uuid:message_id>/<str:media_type>/', chat_media_file_page, name='chat_media_file'),
    path('messages/<uuid:conversation_id>/upload/', chat_media_upload_page, name='chat_media_upload'),
]


"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"