from rest_framework import serializers

from apps.companies.models import Company

from .models import User
from .roles import Role


class MeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    company = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "role",
            "company",
        ]

    def get_company(self, user):
        if user.company_id is None:
            return None
        return {"id": user.company_id, "name": user.company.name}


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    company = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(), required=False, allow_null=True
    )
    company_name = serializers.CharField(source="company.name", read_only=True, default=None)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "company",
            "company_name",
            "is_active",
            "password",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        actor = self.context["request"].user
        role = attrs.get("role", getattr(self.instance, "role", Role.VIEWER))

        if actor.role == Role.COMPANY_ADMIN:
            if role == Role.VEZAPP_ADMIN:
                raise serializers.ValidationError({"role": "You cannot assign this role."})
            # A Company Admin can only ever work inside their own company.
            attrs["company"] = actor.company
        else:
            company = attrs.get("company", getattr(self.instance, "company", None))
            if role == Role.VEZAPP_ADMIN:
                attrs["company"] = None
            elif company is None:
                raise serializers.ValidationError(
                    {"company": "A company is required for this role."}
                )

        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "A password is required."})

        # Nobody locks themselves out: no deactivating or changing the role of your own account.
        if self.instance is not None and self.instance.pk == actor.pk:
            if attrs.get("is_active") is False:
                raise serializers.ValidationError(
                    {"is_active": "You cannot deactivate your own account."}
                )
            if "role" in attrs and attrs["role"] != self.instance.role:
                raise serializers.ValidationError(
                    {"role": "You cannot change the role of your own account."}
                )
        return attrs

    def validate_password(self, value):
        from django.contrib.auth.password_validation import validate_password

        try:
            validate_password(value)
        except Exception as exc:  # django ValidationError -> DRF
            messages = getattr(exc, "messages", [str(exc)])
            raise serializers.ValidationError(messages) from exc
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
