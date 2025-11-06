File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/app.py", line 917, in full_dispatch_request
    rv = self.dispatch_request()
         ^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/app.py", line 902, in dispatch_request
    return self.ensure_sync(self.view_functions[rule.endpoint])(**view_args)  # type: ignore[no-any-return]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/bot.py", line 281, in webhook_telegram
    update = Update.de_json(request.get_json(force=True), app.bot)
                                                          ^^^
NameError: name 'app' is not defined
127.0.0.1 - - [06/Nov/2025:20:38:25 +0000] "POST /webhook_telegram HTTP/1.1" 500 265 "-" "-"
[2025-11-06 20:40:15,870] ERROR in app: Exception on /webhook_telegram [POST]
127.0.0.1 - - [06/Nov/2025:20:40:15 +0000] "POST /webhook_telegram HTTP/1.1" 500 265 "-" "-"
Traceback (most recent call last):
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/app.py", line 1511, in wsgi_app
    response = self.full_dispatch_request()
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/app.py", line 919, in full_dispatch_request
    rv = self.handle_user_exception(e)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/app.py", line 917, in full_dispatch_request
    rv = self.dispatch_request()
         ^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/app.py", line 902, in dispatch_request
    return self.ensure_sync(self.view_functions[rule.endpoint])(**view_args)  # type: ignore[no-any-return]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/bot.py", line 281, in webhook_telegram
    update = Update.de_json(request.get_json(force=True), app.bot)
                                                          ^^^
NameError: name 'app' is not defined
     ==> Deploying...
==> Running 'gunicorn bot:flask_app'
Traceback (most recent call last):
  File "/opt/render/project/src/.venv/bin/gunicorn", line 8, in <module>
    sys.exit(run())
             ^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/wsgiapp.py", line 66, in run
    WSGIApplication("%(prog)s [OPTIONS] [APP_MODULE]", prog=prog).run()
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/base.py", line 235, in run
    super().run()
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/base.py", line 71, in run
    Arbiter(self).run()
    ^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/arbiter.py", line 57, in __init__
    self.setup(app)
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/arbiter.py", line 117, in setup
    self.app.wsgi()
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/base.py", line 66, in wsgi
    self.callable = self.load()
                    ^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/wsgiapp.py", line 57, in load
    return self.load_wsgiapp()
           ^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/wsgiapp.py", line 47, in load_wsgiapp
    return util.import_app(self.app_uri)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/util.py", line 370, in import_app
    mod = importlib.import_module(module)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/python/Python-3.11.9/lib/python3.11/importlib/__init__.py", line 126, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap>", line 1204, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1176, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1147, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 690, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 936, in exec_module
  File "<frozen importlib._bootstrap_external>", line 1074, in get_code
  File "<frozen importlib._bootstrap_external>", line 1004, in source_to_code
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/opt/render/project/src/bot.py", line 229
    lista = "\n".join(str(u)
                     ^
SyntaxError: '(' was never closed
     ==> Exited with status 1
     ==> Common ways to troubleshoot your deploy: https://render.com/docs/troubleshooting-deploys
[2025-11-06 20:41:42,188] ERROR in app: Exception on /webhook_telegram [POST]
Traceback (most recent call last):
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/app.py", line 1511, in wsgi_app
    response = self.full_dispatch_request()
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/app.py", line 919, in full_dispatch_request
    rv = self.handle_user_exception(e)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/app.py", line 917, in full_dispatch_request
    rv = self.dispatch_request()
         ^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/app.py", line 902, in dispatch_request
    return self.ensure_sync(self.view_functions[rule.endpoint])(**view_args)  # type: ignore[no-any-return]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/bot.py", line 281, in webhook_telegram
    update = Update.de_json(request.get_json(force=True), app.bot)
                                                          ^^^
NameError: name 'app' is not defined
127.0.0.1 - - [06/Nov/2025:20:41:42 +0000] "POST /webhook_telegram HTTP/1.1" 500 265 "-" "-"
==> Running 'gunicorn bot:flask_app'
Traceback (most recent call last):
  File "/opt/render/project/src/.venv/bin/gunicorn", line 8, in <module>
    sys.exit(run())
             ^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/wsgiapp.py", line 66, in run
    WSGIApplication("%(prog)s [OPTIONS] [APP_MODULE]", prog=prog).run()
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/base.py", line 235, in run
    super().run()
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/base.py", line 71, in run
    Arbiter(self).run()
    ^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/arbiter.py", line 57, in __init__
    self.setup(app)
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/arbiter.py", line 117, in setup
    self.app.wsgi()
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/base.py", line 66, in wsgi
    self.callable = self.load()
                    ^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/wsgiapp.py", line 57, in load
    return self.load_wsgiapp()
           ^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/app/wsgiapp.py", line 47, in load_wsgiapp
    return util.import_app(self.app_uri)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/gunicorn/util.py", line 370, in import_app
    mod = importlib.import_module(module)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/python/Python-3.11.9/lib/python3.11/importlib/__init__.py", line 126, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap>", line 1204, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1176, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1147, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 690, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 936, in exec_module
  File "<frozen importlib._bootstrap_external>", line 1074, in get_code
  File "<frozen importlib._bootstrap_external>", line 1004, in source_to_code
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/opt/render/project/src/bot.py", line 229
    lista = "\n".join(str(u)
                     ^
SyntaxError: '(' was never closed
