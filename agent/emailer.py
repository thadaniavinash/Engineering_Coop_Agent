"""Daily email digest, sent through Gmail with an app password (free)."""
from __future__ import annotations
import html
import os
import smtplib
import ssl
from email.message import EmailMessage

TERM = {"16": "16 mo", "12": "12 mo", "12-16": "12–16 mo", "other": "4/8 mo", "unclear": "Term unclear"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _start(s):
    if not s or s == "unclear":
        return "Start unclear"
    y, m = s.split("-")
    return f"Starts {MONTHS[int(m) - 1]} {y}"


def _row(r):
    e = html.escape
    bits = [f"{r['km']} km" if r.get("km") is not None else "distance unknown", TERM.get(r["term"], r["term"]), _start(r["start"])]
    if r.get("pay"):
        bits.append(f"${r['pay'][0]:g}–{r['pay'][1]:g}/h")
    if r.get("deadline"):
        bits.append(f"apply by {r['deadline']}")
    flag = ""
    if r["term"] == "unclear" or r["start"] == "unclear":
        flag = ' <span style="background:#FBEEDA;color:#8A5200;border-radius:9px;padding:1px 7px;font-size:11px">Needs check</span>'
    summary = f'<div style="color:#44525c;font-size:13px;margin-top:3px">{e(r["summary"])}</div>' if r.get("summary") else ""
    return (f'<tr><td style="padding:10px 12px 10px 0;vertical-align:top;font:700 20px/1 Arial;color:#0E6B7F;width:40px">{r["_score"]}</td>'
            f'<td style="padding:10px 0;border-bottom:1px solid #e3e8e7">'
            f'<a href="{e(r["url"])}" style="color:#15212B;font-weight:600;font-size:15px;text-decoration:none">{e(r["title"])}</a>{flag}'
            f'<div style="color:#5A6873;font-size:13px">{e(r["company"])} · {e(r.get("city") or r.get("location") or "Ontario")}</div>'
            f'<div style="font:12px Consolas,monospace;color:#15212B;margin-top:3px">{" · ".join(e(b) for b in bits)}</div>{summary}</td></tr>')


def build(new, closing, top, meta, site_url, first_run=False) -> tuple[str, str]:
    n = len(new)
    if first_run:
        subject = f"Co-op Scout is live: {n} listings found on the first run"
    elif n:
        subject = f"Co-op Scout: {n} new co-op listing{'s' if n != 1 else ''}"
    else:
        subject = "Co-op Scout: weekly roundup"
    parts = [f'<div style="font-family:Arial,Helvetica,sans-serif;max-width:680px;color:#15212B">',
             f'<h1 style="font-size:22px;letter-spacing:.02em;margin:0 0 4px">CO-OP SCOUT</h1>',
             f'<p style="color:#5A6873;margin:0 0 16px">{html.escape(meta["run_label"])} · '
             f'<a href="{site_url}" style="color:#0E6B7F">Open the full list on the website</a></p>']
    if new:
        parts.append(f'<h2 style="font-size:16px;border-bottom:2px solid #15212B;padding-bottom:4px">New since the last run ({n})</h2><table style="border-collapse:collapse;width:100%">')
        parts += [_row(r) for r in new]
        parts.append("</table>")
    if closing:
        parts.append('<h2 style="font-size:16px;border-bottom:2px solid #15212B;padding-bottom:4px;margin-top:22px">Closing within 7 days</h2><table style="border-collapse:collapse;width:100%">')
        parts += [_row(r) for r in closing]
        parts.append("</table>")
    if top:
        parts.append('<h2 style="font-size:16px;border-bottom:2px solid #15212B;padding-bottom:4px;margin-top:22px">Top 10 overall this week</h2><table style="border-collapse:collapse;width:100%">')
        parts += [_row(r) for r in top]
        parts.append("</table>")
    s = meta["source_counts"]
    parts.append(f'<p style="color:#5A6873;font-size:12px;margin-top:22px">Checked {s["ok"]} sources successfully'
                 f'{", " + str(s["failed"]) + " could not be read" if s["failed"] else ""}. '
                 f'The score (0–100) uses the default "Balanced" weights; change them on the website. '
                 f'"Needs check" means the posting doesn\'t clearly state a 12/16-month term or a start date.</p></div>')
    return subject, "".join(parts)


def send(subject: str, body_html: str) -> str:
    user, pw, to = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD"), os.environ.get("EMAIL_TO")
    if not (user and pw and to):
        return "email not configured (GMAIL_ADDRESS / GMAIL_APP_PASSWORD / EMAIL_TO secrets missing)"
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, f"Co-op Scout <{user}>", to
    msg.set_content("This email is best viewed in HTML. Open the website for the full list.")
    msg.add_alternative(body_html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, pw.replace(" ", ""))
        s.send_message(msg)
    return f"sent to {to.count(',') + 1} recipient(s)"


def send_alert(subject: str, text: str) -> str:
    return send(subject, f"<div style='font-family:Arial'><p>{html.escape(text)}</p></div>")
