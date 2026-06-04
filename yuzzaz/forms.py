from django import forms
from .models import CustomUser

class UserRegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
        label="Password"
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}),
        label="Confirm Password"
    )

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'telephone']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
        }

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match!")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.username = self.cleaned_data["email"]  # Set the username to email
        if commit:
            user.save()
        return user


# class CustomUserForm(forms.ModelForm):
#     telephone = forms.RegexField(regex=r'^\+?\d{9,15}$', error_messages={
#     'invalid': "Enter a valid international phone number."
#         })
#     class Meta:
#         model = CustomUser
#         fields = ['first_name', 'last_name', 'email', 'telephone',  'profile_picture', 'bio', 'school', 'instagram_username']
#         widgets = {
#             'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
#             'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
#             'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            
#         }



from django import forms
from .models import CustomUser
import re

class CustomUserForm(forms.ModelForm):
    telephone = forms.RegexField(
        regex=r'^\+?\d{9,15}$',
        error_messages={'invalid': "Enter a valid international phone number (e.g., +255123456789)."},
        widget=forms.TextInput(attrs={
            'class': 'input-field',
            'placeholder': '+255123456789'
        })
    )
    
    
    class Meta:
        model = CustomUser
        # Email is intentionally excluded — it's the verified identity, render
        # it read-only in the template instead of allowing edits.
        fields = ['first_name', 'last_name', 'telephone', 'profile_picture']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'input-field',
                'placeholder': 'First Name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'input-field',
                'placeholder': 'Last Name'
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': '',
                'id': 'profile-picture-input'
            }),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        return user