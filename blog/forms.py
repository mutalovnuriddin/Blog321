from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    SetPasswordForm,
    UserCreationForm,
)
from .models import Profile, Post, Comment

class ProfileCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Profile
        fields = ('username', 'email', 'phone_number')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            'username': 'Masalan, ali_123',
            'email': 'siz@example.com',
            'phone_number': '+998 90 123 45 67',
            'password1': 'Kamida 8 ta belgidan iborat parol',
            'password2': 'Parolni qayta kiriting',
        }
        labels = {
            'username': 'Foydalanuvchi nomi',
            'email': 'Elektron pochta',
            'phone_number': 'Telefon (ixtiyoriy)',
            'password1': 'Parol',
            'password2': 'Parolni tasdiqlang',
        }
        help_texts = {
            'username': '150 ta belgigacha: lotin harflari, raqamlar va @/./+/-/_ belgilaridan foydalaning.',
            'password1': 'Parol kamida 8 ta belgidan iborat bo‘lsin va keng tarqalgan parollardan foydalanmang.',
            'password2': 'Tasdiqlash uchun avvalgi parolni qayta kiriting.',
        }
        for name, field in self.fields.items():
            field.label = labels.get(name, field.label)
            field.help_text = help_texts.get(name, '')
            field.widget.attrs.update({
                'class': 'form-input',
                'placeholder': placeholders.get(name, ''),
                'autocomplete': 'new-password' if name.startswith('password') else 'off',
            })

        self.fields['username'].widget.attrs['autocomplete'] = 'username'
        self.fields['email'].widget.attrs['autocomplete'] = 'email'
        self.fields['email'].required = True
        self.fields['phone_number'].required = False


class ProfileLoginForm(AuthenticationForm):
    username = forms.CharField(
        label='Foydalanuvchi nomi',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Foydalanuvchi nomingiz',
            'autocomplete': 'username',
            'autofocus': True,
        }),
    )
    password = forms.CharField(
        label='Parol',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Parolingiz',
            'autocomplete': 'current-password',
        }),
    )


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = (
            'first_name',
            'last_name',
            'username',
            'email',
            'phone_number',
            'bio',
            'avatar',
        )
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'edit-input',
                'autocomplete': 'given-name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'edit-input',
                'autocomplete': 'family-name',
            }),
            'username': forms.TextInput(attrs={
                'class': 'edit-input',
                'autocomplete': 'username',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'edit-input',
                'autocomplete': 'email',
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'edit-input',
                'autocomplete': 'tel',
            }),
            'bio': forms.Textarea(attrs={
                'class': 'edit-input edit-textarea',
                'rows': 4,
                'maxlength': 500,
            }),
            'avatar': forms.FileInput(attrs={
                'class': 'edit-file-input',
                'accept': 'image/*',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].label = 'Ism'
        self.fields['last_name'].label = 'Familiya'
        self.fields['username'].label = 'Foydalanuvchi nomi'
        self.fields['email'].label = 'Elektron pochta'
        self.fields['phone_number'].label = 'Telefon raqami'
        self.fields['phone_number'].required = False
        self.fields['bio'].label = 'Men haqimda'
        self.fields['bio'].required = False
        self.fields['avatar'].label = 'Profil rasmi'
        self.fields['avatar'].required = False


class ProfilePasswordFormMixin:
    labels = {
        'old_password': 'Joriy parol',
        'new_password1': 'Yangi parol',
        'new_password2': 'Yangi parolni tasdiqlang',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.label = self.labels.get(name, field.label)
            field.widget.attrs.update({
                'class': 'edit-input',
                'autocomplete': 'current-password' if name == 'old_password' else 'new-password',
                'placeholder': 'Parolingizni kiriting',
            })

        if 'new_password1' in self.fields:
            self.fields['new_password1'].help_text = (
                'Yangi parol kamida 8 ta belgidan iborat bo‘lsin.'
            )


class ProfilePasswordChangeForm(ProfilePasswordFormMixin, PasswordChangeForm):
    pass


class ProfileSetPasswordForm(ProfilePasswordFormMixin, SetPasswordForm):
    pass



class PostCreatedForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['title', 'desc', 'img', 'video']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'social-input',
                'placeholder': 'Sarlavha (ixtiyoriy)',
                'maxlength': 255,
            }),
            'desc': forms.Textarea(attrs={
                'class': 'social-input',
                'rows': 4,
                'placeholder': 'Bugun nimalar bilan bo‘lishmoqchisiz?',
            }),
            'img': forms.ClearableFileInput(attrs={
                'class': 'social-file',
                'accept': 'image/*',
            }),
            'video': forms.ClearableFileInput(attrs={
                'class': 'social-file',
                'accept': 'video/*',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].label = 'Sarlavha'
        self.fields['desc'].label = 'Matn'
        self.fields['img'].label = 'Rasm'
        self.fields['video'].label = 'Video'
        for field in self.fields.values():
            field.required = False

    def clean(self):
        cleaned_data = super().clean()
        if not any((
            cleaned_data.get('title'),
            cleaned_data.get('desc'),
            cleaned_data.get('img'),
            cleaned_data.get('video'),
        )):
            raise forms.ValidationError('Post uchun matn, rasm yoki video kiriting.')
        return cleaned_data




class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'social-input',
                'rows': 2,
                'placeholder': 'Fikringizni yozing...',
                'aria-label': 'Izoh matni',
            }),
        }

    def clean_text(self):
        text = self.cleaned_data['text'].strip()
        if not text:
            raise forms.ValidationError('Izoh matni bo\'sh bo\'lmasligi kerak')
        return text