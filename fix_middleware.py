content = open('/app/app/core/privacy_middleware.py').read()

old1 = 'response.headers.pop("Server", None)'
old2 = 'response.headers.pop("X-Powered-By", None)'

new1 = 'pass  # server header removal disabled'
new2 = 'pass  # x-powered-by header removal disabled'

content = content.replace(old1, new1).replace(old2, new2)

open('/app/app/core/privacy_middleware.py', 'w').write(content)
print('Done - replaced', content.count('pass  # server header') + content.count('pass  # x-powered-by'), 'lines')