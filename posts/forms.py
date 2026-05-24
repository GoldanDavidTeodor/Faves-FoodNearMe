from django import forms
from .models import Post, Profile, Tag


class PostForm(forms.ModelForm):
    tags = forms.CharField(
        required=False,
        label="Tags",
        widget=forms.TextInput(attrs={
            "placeholder": "sweet, sour, salty",
        }),
    )

    class Meta:
        model = Post
        fields = ["title", "description", "address_text", "price", "lat", "lng"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "price" in self.fields:
            self.fields["price"].widget.attrs.update({
                "placeholder": "",
                "inputmode": "decimal",
                "step": "0.01",
                "min": "0",
            })
        if self.instance and self.instance.pk:
            existing = list(self.instance.tags.order_by("name").values_list("name", flat=True))
            self.fields["tags"].initial = ", ".join(existing)

    def clean_tags(self):
        raw = (self.cleaned_data.get("tags") or "").strip()
        if not raw:
            return []

        parts = [p.strip().lower() for p in raw.split(",")]
        tags = [p for p in parts if p]

        deduped = []
        seen = set()
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                deduped.append(tag)

        if len(deduped) > 20:
            raise forms.ValidationError("Please use 20 tags or fewer.")

        for tag in deduped:
            if len(tag) > 50:
                raise forms.ValidationError("Each tag must be 50 characters or fewer.")

        return deduped

    def apply_tags(self, post: Post) -> None:
        tag_names = self.cleaned_data.get("tags") or []
        if post.pk is None:
            raise ValueError("post must be saved before applying tags")

        tag_objs = []
        for name in tag_names:
            tag, _ = Tag.objects.get_or_create(name=name)
            tag_objs.append(tag)

        post.tags.set(tag_objs)


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["avatar"]
        widgets = {
            "avatar": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }


class MessageForm(forms.Form):
    text = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(attrs={
            "rows": 1,
            "placeholder": "",
            "maxlength": "2000",
            "required": True,
        }),
    )