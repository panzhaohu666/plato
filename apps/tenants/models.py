"""
Tenant and User models for Plato multi-tenant architecture.

Tenant: one PostgreSQL schema per organization.
User: belongs to a tenant, uses JWT authentication.
"""
from django.db import models
from django.contrib.auth.models import AbstractUser
from django_tenants.models import TenantMixin, DomainMixin


class Tenant(TenantMixin):
    """Organization tenant — each gets its own PostgreSQL schema."""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Tenant config (JSON blob for future extensibility)
    config = models.JSONField(default=dict, blank=True)

    # Is this tenant active?
    is_active = models.BooleanField(default=True)

    # Default true — creates schema on save
    auto_create_schema = True
    auto_drop_schema = True  # Clean up when tenant is deleted

    class Meta:
        db_table = "tenant"

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    """Domain mapping for tenant routing."""
    # django-tenants uses domain to route requests to tenant schemas
    pass


class User(AbstractUser):
    """Custom user model with tenant affiliation and JWT support."""
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
        help_text="The tenant (organization) this user belongs to",
    )

    # Extend with profile fields
    display_name = models.CharField(max_length=200, blank=True, default="")
    avatar_url = models.URLField(blank=True, default="")

    # Permissions
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("editor", "Editor"),
        ("viewer", "Viewer"),
    ]
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="editor",
    )

    class Meta:
        db_table = "user"

    def __str__(self):
        return f"{self.username} ({self.tenant})"
