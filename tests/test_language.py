"""Language Lock: detection, and the drift-and-correct flow."""

import pytest
import language_lock
from language_lock import detect as D


@pytest.mark.parametrize("text,lang", [
    ("Can you fix the login page? It shows an error when I click the button.", "en"),
    ("¿Puedes arreglar la página de inicio? Muestra un error cuando hago clic en el botón.", "es"),
    ("Peux-tu corriger la page de connexion ? Elle affiche une erreur quand je clique.", "fr"),
    ("Kannst du die Login-Seite reparieren? Sie zeigt einen Fehler, wenn ich auf den Knopf klicke.", "de"),
    ("Você pode corrigir a página de login? Ela mostra um erro quando eu clico no botão.", "pt"),
    ("请帮我修复登录页面，点击按钮时会显示错误。", "zh"),
    ("ログインページを直してください。ボタンを押すとエラーが出ます。", "ja"),
    ("로그인 페이지를 고쳐 주세요. 버튼을 누르면 오류가 나요.", "ko"),
    ("Исправь, пожалуйста, страницу входа: при нажатии на кнопку появляется ошибка.", "ru"),
    ("कृपया लॉगिन पेज ठीक करें, बटन दबाने पर त्रुटि आती है।", "hi"),
    ("يرجى إصلاح صفحة تسجيل الدخول، يظهر خطأ عند النقر على الزر.", "ar"),
])
def test_detect(text, lang):
    assert D.detect(text) == lang


def test_code_and_links_do_not_count():
    text = "Hecho. ```python\ndef the_function_is_here(): return the_value\n``` Ya está listo y funciona muy bien con el botón."
    assert D.detect(text) == "es"
    assert D.detect("```js\nconst x = require('the-thing')\n```") is None


def test_too_short_to_tell():
    assert D.detect("ok") is None and D.detect("👍") is None


class FakeCtx:
    def __init__(self, settings=None):
        self.settings, self.hooks, self.commands = settings or {}, {}, {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, cb, **_):
        self.hooks.setdefault(name, []).append(cb)

    def register_command(self, name, handler, **_):
        self.commands[name] = handler

    def fire(self, name, **kw):
        return [cb(**kw) for cb in self.hooks.get(name, [])]


@pytest.fixture
def ctx():
    fake = FakeCtx()
    language_lock.register(fake)
    return fake


EN_USER = "Please look at the logs and tell me why the upload is failing."
EN_REPLY = "The upload fails because the token has expired. I refreshed it and the upload works now."
ZH_REPLY = "上传失败是因为令牌已过期。我已经刷新了令牌，现在上传可以正常工作了。"
ES_USER = "¿Por qué falla la subida de archivos? Revisa los registros por favor."
ES_REPLY = "La subida falla porque el token ha caducado. Lo he renovado y ahora funciona bien."


def turn(ctx, user, reply, session="S1"):
    pre = ctx.fire("pre_llm_call", session_id=session, user_message=user)[0]
    ctx.fire("post_llm_call", session_id=session, assistant_response=reply)
    return pre


def test_staying_in_language_adds_nothing(ctx):
    assert turn(ctx, EN_USER, EN_REPLY) is None
    assert turn(ctx, EN_USER, EN_REPLY) is None


def test_drift_is_corrected_on_the_next_turn(ctx):
    turn(ctx, EN_USER, EN_REPLY)
    turn(ctx, "and the download?", ZH_REPLY)                      # the reply drifted into Chinese
    fix = turn(ctx, "why?", EN_REPLY)
    assert fix and "Your last reply was in Chinese, but the user writes in English" in fix["context"]
    assert turn(ctx, EN_USER, EN_REPLY) is None                   # fixed: nothing more to say
    status = ctx.commands["lang"]("", session_id="S1")
    assert "your language is English (from your messages)" in status and "Drifts caught: 1. Corrections sent: 1." in status


def test_spanish_user_gets_spanish(ctx):
    turn(ctx, ES_USER, EN_REPLY)
    fix = turn(ctx, ES_USER, ES_REPLY)
    assert "Reply in Spanish" in fix["context"]


def test_asking_for_another_language_is_respected(ctx):
    turn(ctx, EN_USER, EN_REPLY)
    assert turn(ctx, "Please translate this paragraph into Chinese for me.", ZH_REPLY) is None
    assert turn(ctx, EN_USER, EN_REPLY) is None


def test_user_who_switches_language_is_followed(ctx):
    for _ in range(2):
        turn(ctx, EN_USER, EN_REPLY)
    turn(ctx, ES_USER, ES_REPLY)
    turn(ctx, ES_USER, ES_REPLY)
    assert ctx.commands["lang"]("", session_id="S1").startswith("Language Lock: your language is Spanish")


def test_set_and_auto(ctx):
    cmd = ctx.commands["lang"]
    assert "expects Hindi" in cmd("set hi", session_id="S1")
    assert "expects German" in cmd("set German", session_id="S1")
    turn(ctx, EN_USER, EN_REPLY)
    assert "Reply in German" in turn(ctx, EN_USER, EN_REPLY)["context"]
    assert "again" in cmd("auto", session_id="S1")
    assert "Unknown language" in cmd("set klingon", session_id="S1") and "Usage" in cmd("x", session_id="S1")


def test_language_and_remind_settings():
    fake = FakeCtx({"language": "es", "remind": "always"})
    language_lock.register(fake)
    assert "Reply in Spanish, the user's language." in turn(fake, EN_USER, ES_REPLY)["context"]


def test_unknown_language_says_so(ctx):
    assert "not sure of your language yet" in ctx.commands["lang"]("", session_id="S9")


def test_sessions_are_separate(ctx):
    turn(ctx, EN_USER, ZH_REPLY, session="A")
    assert turn(ctx, ES_USER, ES_REPLY, session="B") is None


def test_hooks_never_raise_on_junk(ctx):
    assert ctx.fire("pre_llm_call", user_message=None) == [None]
    assert ctx.fire("post_llm_call", assistant_response=None) == [None]
