from django.urls import path

from . import views

urlpatterns = [
    path("admin/users", views.UsersView.as_view()),
    path("admin/users/<int:user_id>/sanctions", views.UserSanctionView.as_view()),
    path("admin/users/<int:user_id>/release", views.UserReleaseView.as_view()),
    path("admin/posts", views.PostsView.as_view()),
    path("admin/posts/<int:post_id>", views.PostDetailView.as_view()),
    path("admin/comments", views.CommentsView.as_view()),
    path("admin/guestbook", views.GuestbookView.as_view()),
]

for name, target in [("posts", "post"), ("comments", "comment"), ("guestbook", "guestbook")]:
    urlpatterns += [
        path(f"admin/{name}/<int:item_id>/hide", views.HideView.as_view(target_type=target)),
        path(f"admin/{name}/<int:item_id>/unhide", views.HideView.as_view(target_type=target, unhide=True)),
    ]
