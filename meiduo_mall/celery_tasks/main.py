from celery import Celery

# 为celery使用django配置文件进行设置
import os
if not os.getenv('DJANGO_SETTINGS_MODULE'):
    os.environ['DJANGO_SETTINGS_MODULE'] = 'meiduo_mall.settings.dev'

# 创建celery应用
app = Celery('meiduo')
app.config_from_object('celery_tasks.config')

# 自动注册celery任务
app.autodiscover_tasks(['celery_tasks.sms', 'celery_tasks.email'])


# 开启celery的命令
# celery -A 应用路径(.包路径) worker -l info
# celery -A celery_tasks.main worker -l info