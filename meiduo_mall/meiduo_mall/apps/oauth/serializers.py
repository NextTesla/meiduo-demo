from rest_framework import serializers
from django_redis import get_redis_connection

from .models import OAuthQQUser
from users.models import User


class OAuthQQUserSerializer(serializers.Serializer):
    """
    QQ登录创建用户序列化器
    """
    access_token = serializers.CharField(label='操作凭证')
    mobile = serializers.RegexField(label='手机号', regex=r'^1[3-9]\d{9}$')
    password = serializers.CharField(label='密码', min_length=8, max_length=20)
    sms_code = serializers.CharField(label='短信验证码')

    def validate(self, attrs):
        access_token = attrs['access_token']
        openid = OAuthQQUser.check_save_user_token(access_token)
        if not openid:
            raise serializers.ValidationError('无效的access_token')

        # 存入openid
        attrs['openid'] = openid

        # 检验短信验证码
        mobile = attrs['mobile']
        sms_code = attrs['sms_code']
        redis_conn = get_redis_connection('verify_codes')
        real_sms_code = redis_conn.get('sms_%s' % mobile)
        if real_sms_code.decode() != sms_code:
            raise serializers.ValidationError('短信验证码错误')

        try:
            user = User.objects.get(mobile=mobile)
        except User.DoesNotExist:
            pass
        else:
            # 如果用户存在，检查用户密码
            password = attrs['password']
            if not user.check_password(password):
                raise serializers.ValidationError('密码错误')
            attrs['user'] = user
        return attrs

    def create(self, validated_data):
        user = validated_data.get('user')
        if not user:
            user = User.objects.create_user(
                username=validated_data['mobile'],
                password=validated_data['password'],
                mobile=validated_data['mobile']
            )

        # 保存用户与第三方QQ认证表的对应关系
        OAuthQQUser.objects.create(
            openid=validated_data['openid'],
            user=user
        )
        return user
