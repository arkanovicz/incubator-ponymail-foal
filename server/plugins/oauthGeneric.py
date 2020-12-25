# Generic OAuth plugin
import re
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

async def process(formdata, session, server):
    formdata["client_id"] = server.config.oauth.client_id
    formdata["client_secret"] = server.config.oauth.client_secret
    formdata["grant_type"] = "authorization_code"
    formdata["return_type"] = "code"
    formdata["redirect_uri"] = server.config.oauth.redirect_uri . "?key=" . formdata["key"]
    js = None
    m = re.match(r"https?://(.+)/", formdata["oauth_token"])
    if m:
        oauth_domain = m.group(1)
        headers = {"User-Agent": "Pony Mail OAuth Agent/0.1"}
        # This is a synchronous process, so we offload it to an async runner in order to let the main loop continue.
        rv = await server.runners.run(
            requests.post, formdata["oauth_token"], headers=headers, data=formdata, verify=False
        )
        js = rv.json()
        js["oauth_domain"] = oauth_domain
        js["authoritative"] = True
    return js
