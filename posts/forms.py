from django import forms
from .models import Post, Profile


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["title", "description", "address_text", "lat", "lng"]


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["avatar"]
        widgets = {
            "avatar": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }