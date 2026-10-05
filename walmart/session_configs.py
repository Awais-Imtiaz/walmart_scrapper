from scrapy_zyte_api import SessionConfig, session_config


@session_config(["www.walmart.com"])
class WalmartSessionConfig(SessionConfig):
    """Session warm-up for walmart.com.

    No setLocation here, even though Zyte reports the action as "success"
    on walmart.com: the site resolves your store from the session IP, not
    from the browser geolocation override. Sessions both typed zip 10001
    and 90210 came back "Sacramento 95829 / store 3081" — the datacenter
    default (docs/00-phase0-discovery.md R2/R3). Warming with a plain
    browserHtml request still pays off: sessions with cookie history saw
    noticeably fewer challenge shells in the experiment log.
    """

    def params(self, request):
        return {"browserHtml": True}

    def check(self, response, request):
        # Challenge shells are common on walmart.com; discarding a session
        # over one shell would churn pools for nothing — Scrapy retries
        # handle them (see middlewares.WalmartShellDetectorMiddleware).
        return True
