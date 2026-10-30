from django.conf import settings
from django.db import models

from apps.core.models import CompanyScopedModel


class AssistantLog(CompanyScopedModel):
    """Every question put to the assistant: what was asked, which tools ran, what came back.

    Never holds keys or tokens, only the question, tool names and arguments, and the answer.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    username = models.CharField(max_length=150, blank=True)
    kind = models.CharField(max_length=10, default="ask")  # ask | explain | summary
    # Questions of one chat share an id, so a follow-up can be understood. Held on the server, so
    # nobody can forge what the assistant said earlier.
    conversation = models.CharField(max_length=32, blank=True, db_index=True)
    mode = models.CharField(max_length=10)  # basic | ai
    prompt = models.CharField(max_length=600)
    tool_calls = models.JSONField(default=list, blank=True)
    answer = models.TextField(blank=True)
    flagged = models.BooleanField(default=False)  # the model's answer failed the number check
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["user", "-id"])]

    def __str__(self):
        return f"{self.username}: {self.prompt[:40]}"
