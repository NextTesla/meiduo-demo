from django.shortcuts import render
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView, CreateAPIView
from rest_framework.viewsets import GenericViewSet
from rest_framework import mixins
from django_redis import get_redis_connection
from django.http.response import HttpResponse
from rest_framework.response import Response
import random

from meiduo_mall.libs.captcha.captcha import captcha
from verifications import constants
from . import serializers
from celery_tasks.sms.tasks import send_sms_code
from users.models import User

# Create your views here.


class ImageCodeView(APIView):
    """
    图片验证码
    """
    def get(self, request, image_code_id):
        """
        获取图片验证码
        """

        # 生成验证码图片
        text, image = captcha.generate_captcha()

        # 获取redis连接对象
        redis_conn = get_redis_connection('verify_codes')
        # 将图片验证码 按照 【img_id：text】形式存入redis中
        redis_conn.setex("img_%s" % image_code_id, constants.IMAGE_CODE_REDIS_EXPIRES, text)

        return HttpResponse(image, content_type="images/jpg")


class SMSCodeView(GenericAPIView):
    """
    短信验证码
    """
    serializer_class = serializers.CheckImageCodeSerializer

    def get(self, request, mobile):
        # 校验图片验证码和发送短信的频次
        # mobile是被放到了类视图对象属性kwargs中
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        # 校验通过
        # 生成短信验证码
        sms_code = '%06d' % random.randint(0, 999999)

        # 保存验证码及发送记录
        redis_conn = get_redis_connection('verify_codes')
        # redis_conn.setex('sms_%s' % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        # redis_conn.setex('send_flag_%s' % mobile, constants.SEND_SMS_CODE_INTERVAL, 1)

        # 使用redis的pipeline一次执行多个命令
        pl = redis_conn.pipeline()
        pl.setex('sms_%s' % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        pl.setex('send_flag_%s' % mobile, constants.SEND_SMS_CODE_INTERVAL, 1)
        pl.execute()

        send_sms_code.delay(mobile, sms_code)

        # 返回
        return Response({'message': 'OK'}, status=status.HTTP_200_OK)


class UsernameCountView(APIView):
    """
    用户名数量
    """

    def get(self, request, username):
        """
        获取指定用户名数量
        """
        count = User.objects.filter(username=username).count()

        data = {
            'username': username,
            'count': count
        }

        return Response(data)


class MobileCountView(APIView):
    """
    手机号数量
    """
    def get(self, request, mobile):
        """
        获取指定手机号数量
        """
        count = User.objects.filter(mobile=mobile).count()

        data = {
            'mobile': mobile,
            'count': count
        }

        return Response(data)


class UserView(CreateAPIView):
    """
    用户信息
    """
    serializer_class = serializers.CreateUserSerializer