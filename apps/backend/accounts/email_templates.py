"""
The verification-code email: a branded, RTL HTML message with a plain-text fallback.

Email clients ignore <style> blocks and modern CSS, so this is the classic bulletproof layout: nested
tables, every style inline, system fonts, no remote images (many clients block them by default, and a
hosted logo would also tell a third party when the mail was opened). The "logo" is a styled wordmark.
Colours are the platform's own: navy #313851 on cream #f6f3ed.
"""
from html import escape

NAVY = "#313851"
CREAM = "#f6f3ed"
INK = "#1f2433"
SOFT = "#6b7280"
LINE = "#e6e1d6"
FONT = "Segoe UI, Tahoma, 'Noto Naskh Arabic', 'Noto Sans Arabic', Arial, sans-serif"

SUBJECT = "رمز التحقق من مدار"
VALID_MINUTES = 5


def render_otp_text(code: str) -> str:
    return (
        "مدار\n\n"
        "رمز التحقق الخاص بك:\n"
        f"{code}\n\n"
        f"الرمز صالح لمدة {VALID_MINUTES} دقائق ويُستخدم مرة واحدة فقط.\n"
        "لا تشاركه مع أي شخص — فريق مدار لن يطلبه منك أبدًا.\n\n"
        "إذا لم تطلب هذا الرمز، تجاهل هذه الرسالة؛ حسابك بأمان.\n"
    )


def render_otp_html(code: str) -> str:
    # One box per digit: easy to read aloud and to type, and it survives narrow phone screens.
    digits = "".join(
        f'<td style="padding:0 3px;"><div style="width:40px;height:52px;line-height:52px;text-align:center;'
        f"font-size:26px;font-weight:700;color:{NAVY};background:#ffffff;border:1px solid {LINE};"
        f'border-radius:10px;font-family:Consolas,Menlo,monospace;">{escape(ch)}</div></td>'
        for ch in code
    )
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{SUBJECT}</title>
</head>
<body style="margin:0;padding:0;background:{CREAM};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{CREAM};">
رمز التحقق الخاص بك هو {escape(code)} — صالح لمدة {VALID_MINUTES} دقائق.
</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM};">
<tr><td align="center" style="padding:32px 14px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="max-width:480px;background:#ffffff;border:1px solid {LINE};border-radius:20px;overflow:hidden;">
    <tr><td align="center" style="background:{NAVY};padding:26px 20px;">
      <div style="font-family:{FONT};font-size:34px;font-weight:800;color:#ffffff;letter-spacing:0;">مدار</div>
      <div style="font-family:{FONT};font-size:13px;color:#c9cfe3;margin-top:4px;">منصّة المدرّس الخصوصي</div>
    </td></tr>
    <tr><td style="padding:32px 28px 8px;font-family:{FONT};direction:rtl;text-align:right;">
      <h1 style="margin:0 0 10px;font-size:21px;line-height:1.5;color:{INK};">رمز التحقق الخاص بك</h1>
      <p style="margin:0;font-size:15px;line-height:1.9;color:{SOFT};">
        أدخل الرمز التالي في مدار لإكمال العملية:
      </p>
    </td></tr>
    <tr><td align="center" style="padding:22px 12px 8px;">
      <table role="presentation" cellpadding="0" cellspacing="0" dir="ltr"><tr>{digits}</tr></table>
    </td></tr>
    <tr><td align="center" style="padding:10px 28px 4px;font-family:{FONT};">
      <span style="display:inline-block;font-size:13px;color:{NAVY};background:#eef0f7;border-radius:999px;padding:6px 14px;">
        صالح لمدة {VALID_MINUTES} دقائق · يُستخدم مرة واحدة
      </span>
    </td></tr>
    <tr><td style="padding:24px 28px 30px;font-family:{FONT};direction:rtl;text-align:right;">
      <div style="border-top:1px solid {LINE};padding-top:18px;font-size:13.5px;line-height:1.9;color:{SOFT};">
        <strong style="color:{INK};">لا تشارك هذا الرمز مع أي شخص.</strong>
        فريق مدار لن يطلبه منك أبدًا، لا بالهاتف ولا بالرسائل.<br>
        إذا لم تطلب هذا الرمز فتجاهل الرسالة، حسابك بأمان ولن يتغير شيء.
      </div>
    </td></tr>
  </table>
  <div style="font-family:{FONT};font-size:12px;color:{SOFT};margin-top:16px;">
    رسالة آلية من مدار — من فضلك لا ترد عليها.
  </div>
</td></tr>
</table>
</body>
</html>"""
