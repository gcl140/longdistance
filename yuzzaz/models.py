from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True, verbose_name="Official Email")
    username = models.EmailField(unique=True, blank=True, null=True)  # Use email as the username
    telephone = models.CharField(max_length=15)  # Add telephone field
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    @property
    def nickname(self):
        if self.email:
            return self.email.split('@')[0].lower()
        return self.username
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"
