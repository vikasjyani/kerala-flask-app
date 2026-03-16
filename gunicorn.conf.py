import os

workers = 9
worker_class = "gthread"
threads = 4
timeout = 120
graceful_timeout = 30
preload_app = True
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
accesslog = "-"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sms'
errorlog = "-"
loglevel = "warning"
