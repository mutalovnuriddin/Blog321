from django.contrib import admin
from .models import Notification, Profile
# Register your models here.


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['id', 'username', 'created_at']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'recipient', 'actor', 'verb', 'preview', 'is_read', 'created_at']
    list_filter = ['verb', 'is_read']
    search_fields = ['recipient__username', 'actor__username']