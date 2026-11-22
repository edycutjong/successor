import pytest

from successor.agent import fetch_link as fl

NOTICE = (
    "see [a](https://fetch.ai/blog/post) and [b](http://fetch.ai/x) and [c](https://x.com/a/status/1) "
    "and [d](https://evil.example/p) and [e](https://clearpool.medium.com/p)"
)
ALLOWED = {"fetch.ai"}


@pytest.mark.parametrize(
    "url,reason",
    [
        ("https://fetch.ai/other", "not in the notice"),
        ("http://fetch.ai/x", "https only"),
        ("https://x.com/a/status/1", "allow-list"),
        ("https://evil.example/p", "allow-list"),
    ],
)
def test_refusals(url, reason):
    with pytest.raises(fl.LinkRefused, match=reason):
        fl.check_url(url, NOTICE, ALLOWED)


def test_allowed_hosts():
    assert fl.check_url("https://fetch.ai/blog/post", NOTICE, ALLOWED) == "fetch.ai"
    assert (
        fl.check_url("https://clearpool.medium.com/p", NOTICE, set()) == "clearpool.medium.com"
    )  # fixed host


def test_allow_list_widens_project_domains_not_shared_or_explorer_domains():
    rows = [
        {
            "urls": {
                "website": ["https://www.singularitynet.io/"],
                "explorer": ["https://etherscan.io/token/0x1", "https://explore-fetchhub.fetch.ai/"],
                "message_board": ["https://foo.github.io/blog"],
                "chat": ["https://t.me/x"],
            }
        }
    ]
    hosts = fl.allowed_hosts(rows)
    assert hosts == {"singularitynet.io", "fetch.ai", "foo.github.io"}


async def test_private_dns_answer_is_refused(monkeypatch):
    with pytest.raises(fl.LinkRefused, match="non-public"):
        await fl._public_dns("localhost")


def test_html_to_text_drops_scripts():
    html = "<html><head><title>t</title></head><body><script>bad()</script><p>1 $AGIX to 0.433350 $ASI</p></body>"
    assert fl.html_to_text(html) == "1 $AGIX to 0.433350 $ASI"
