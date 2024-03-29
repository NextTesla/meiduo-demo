from django.shortcuts import render
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from django_redis import get_redis_connection
from django.http.response import HttpResponse
from rest_framework.response import Response
import random
import re

from meiduo_mall.libs.captcha.captcha import captcha
from verifications import constants
from . import serializers
from celery_tasks.sms.tasks import send_sms_code
from users.models import User
from users.utils import get_user_by_account

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


class SMSCodeTokenView(GenericAPIView):
    """
    根据账号和图片验证码，获取发送短信的token
    """
    serializer_class = serializers.CheckImageCodeSerializer

    def get(self, request, account):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        user = get_user_by_account(account)
        if user is None:
            return Response({'message': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)

        access_token = user.generate_send_sms_token()

        mobile = re.sub(r'(\d{3})\d{4}(\d{4})', r'\1****\2', user.mobile)

        return Response({
            'mobile': mobile,
            'access_token': access_token
        })


class SMSCodeByTokenView(APIView):
    """
    短信验证码
    """
    def get(self, request):
        """
        凭借token发送短信验证码
        """

        # 验证access_token
        access_token = request.query_params.get('access_token')
        if not access_token:
            return Response({'message': '缺少access token'}, status=status.HTTP_400_BAD_REQUEST)

        mobile = User.check_send_sms_token(access_token)
        if not mobile:
            return Response({'message': 'access token无效'}, status=status.HTTP_400_BAD_REQUEST)

        # 判断是否在60s内
        redis_conn = get_redis_connection('verify_codes')
        send_flag = redis_conn.get('send_flag_%s' % mobile)
        if send_flag:
            return Response({'message': '请求次数过于频繁'}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # 生成短信验证码
        sms_code = '%06d' % random.randint(0, 999999)

        # 保存短信验证码与发送记录
        pl = redis_conn.pipeline()
        pl.setex("sms_%s" % mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        pl.setex("send_flag_%s" % mobile, constants.SEND_SMS_CODE_INTERVAL, 1)
        pl.execute()

        # 发送短信验证码
        send_sms_code(mobile, sms_code)

        return Response({"message": "OK"}, status=status.HTTP_200_OK)
