import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from .storage import PrivateChatStorage
# Create your models here.


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Profile(AbstractUser, BaseModel):
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', default='avatars/user.png', blank=True, null=True)
    following = models.ManyToManyField('self', symmetrical=False, blank=True)

    def __str__(self):
        return self.username


class Post(BaseModel):
    author = models.ForeignKey(Profile, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    img = models.ImageField(upload_to='posts/image/', blank=True, null=True)
    video = models.FileField(upload_to='posts/videos/', blank=True, null=True)
    likes = models.ManyToManyField(Profile, related_name='likes_posts', blank=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def total_likes(self):
        return self.likes.count()

    def __str__(self):
        return f"{self.author.username} - {self.title or self.desc[:20]}"


class Comment(BaseModel):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='comments')
    text = models.TextField()

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.author.username} -> {self.post.id}: {self.text[:20]}"



class Notification(BaseModel):
    class Verb(models.TextChoices):
        LIKE = 'like', 'Like'
        COMMENT = 'comment', 'Izoh'
        FOLLOW = 'follow', 'Kuzatish'
        MESSAGE = 'message', 'Xabar'

    recipient = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='received_notifications',
    )
    actor = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='sent_notifications',
    )
    verb = models.CharField(max_length=10, choices=Verb.choices)
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    comment = models.ForeignKey(
        'Comment',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    conversation = models.ForeignKey(
        'Conversation',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    preview = models.CharField(max_length=160, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"{self.actor.username} → {self.recipient.username}: {self.verb}"


class Conversation(BaseModel):
    participant_a = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='conversations_as_a')
    participant_b = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='conversations_as_b')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['participant_a', 'participant_b'],
                name='unique_conversation_participants',
            ),
            models.CheckConstraint(
                condition=~models.Q(participant_a=models.F('participant_b')),
                name='conversation_participants_are_distinct',
            ),
        ]
        ordering = ['-updated_at']


    def participant_for(self, user):
        if user.pk == self.participant_a_id:
            return self.participant_b
        if user.pk == self.participant_b_id:
            return self.participant_a
        return None

    def __str__(self):
        return f"{self.participant_a.username} ↔ {self.participant_b.username}"


class DirectMessage(BaseModel):
    class MessageType(models.TextChoices):
        TEXT = 'text', 'Matn'
        IMAGE = 'image', 'Rasm'
        AUDIO = 'audio', 'Ovozli xabar'

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='sent_messages')
    text = models.CharField(max_length=5000, blank=True)
    message_type = models.CharField(
        max_length=10,
        choices=MessageType.choices,
        default=MessageType.TEXT,
    )
    image = models.ImageField(
        upload_to='chat/images/',
        storage=PrivateChatStorage(),
        blank=True,
    )
    audio = models.FileField(
        upload_to='chat/audio/',
        storage=PrivateChatStorage(),
        blank=True,
    )
    edited_at = models.DateTimeField(blank=True, null=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.username}: {self.text[:40]}"