from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/reports/", include("reports.urls")),
]

# Do not expose MEDIA_ROOT through Django's static media handler.
# Medical reports must only be served through authenticated API endpoints.
